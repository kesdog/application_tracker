"""Conservative, idempotent application reconciliation from read-only Gmail evidence."""
from datetime import datetime, timezone
from dataclasses import replace
from email.utils import parsedate_to_datetime
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from bs4 import BeautifulSoup
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import applications
from app.activity import record_event
from app.confirmation_details import extract_confirmation_details
from app.models import ActorType, Application, ApplicationStatus, InvalidationEvent, MailImportReceipt, TimelineEvent
from app.schemas import ApplicationCreate, ApplicationUpdate


def normalized(value):
    value = ''.join(' ' if unicodedata.category(char).startswith('P') else char for char in (value or ''))
    value = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def canonical(value):
    parsed = urlsplit(value or '')
    query = [(key, value) for key, value in parse_qsl(parsed.query) if not key.lower().startswith('utm_') and key.lower() not in ('trk', 'trackingid')]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), urlencode(sorted(query)), ''))


def evidence(message):
    headers = {item['name'].lower(): item['value'] for item in message.get('headers', [])}
    soup = BeautifulSoup(message.get('content', '')[:120000], 'html.parser')
    full_text = soup.get_text(' ', strip=True)
    for quoted in soup.select('blockquote, .gmail_quote, .gmail_extra, .yahoo_quoted, script, style'):
        quoted.decompose()
    fresh = soup.get_text('\n', strip=True)
    fresh = re.split(r'(?im)^\s*(?:On .+ wrote:|Le .+ écrit\s*:|From:|De\s*:|>).*$', fresh, maxsplit=1)[0]
    # Feed only current body text to confirmation extraction; preserve HTML anchors for posting matching.
    details = extract_confirmation_details(fresh or headers.get('subject') or 'Unrecognized email')
    posting = extract_confirmation_details(str(soup) or 'Unrecognized email').posting
    if details.company and not details.job_title and details.kind == 'CV_FORWARDED' and posting.get('job_url'):
        labels = {anchor.get_text(' ', strip=True) for anchor in soup.find_all('a', href=True)
                  if canonical(str(anchor['href'])) == canonical(posting['job_url'])}
        labels = {label for label in labels if 5 <= len(label) <= 300 and not re.match(
            r'^(?:voir|consulter|ouvrir|en savoir|clique[rz]|view|open|read|learn|apply|postuler|candidater)\b', normalized(label))}
        if len(labels) == 1:
            details = replace(details, job_title=labels.pop())
    at = None
    try:
        parsed = parsedate_to_datetime(headers.get('date', ''))
        if parsed.tzinfo is not None:
            at = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        pass
    if at is None:
        try:
            at = datetime.fromtimestamp(int(message['internal_date']) / 1000, timezone.utc).replace(tzinfo=None)
        except (KeyError, ValueError, TypeError, OverflowError, OSError):
            pass
    return headers, fresh, full_text, details, posting, at


def lifecycle(text):
    text = normalized(text)
    if re.search(r'\b(?:candidature n a pas ete retenue|ne donnerons pas suite a votre candidature|votre candidature n est pas retenue|decided not to (?:proceed|move forward) with your application|your application (?:has been|was) unsuccessful|you have not been selected|we regret to inform you .{0,100}(?:not selected|unsuccessful))\b', text):
        return {'status': 'CLOSED', 'outcome': 'UNSUCCESSFUL'}
    if re.search(r'\b(?:invite you to (?:an? )?(?:interview|technical interview)|we would like to schedule (?:an? )?interview|nous vous invitons a (?:un |une )?(?:entretien|rencontre)|nous souhaitons vous rencontrer (?:pour|lors d) un entretien)\b', text):
        return {'status': 'INTERVIEW'}
    return {}


def match_application(session, account, message, headers, full_text, details, posting):
    records = list(session.scalars(select(Application)))
    reference = re.compile(r'(?:\[?Gmail:\s*|/#all/|#all/)([a-f0-9]+)', re.I)
    exact = [app for app in records if message['id'].lower() in [value.lower() for value in reference.findall(app.email_reference or '')]
             or headers.get('message-id', '') and headers['message-id'] in (app.email_reference or '').splitlines()]
    prior = set(session.scalars(select(MailImportReceipt.application_id).where(
        MailImportReceipt.account == account, MailImportReceipt.thread_id == message.get('thread_id'),
        MailImportReceipt.application_id.is_not(None)))) if message.get('thread_id') else set()
    candidates = exact or [app for app in records if app.id in prior]
    if not candidates and posting.get('job_url'):
        candidates = [app for app in records if app.job_url and canonical(app.job_url) == canonical(posting['job_url'])]
    if not candidates and details.company and details.job_title:
        candidates = [app for app in records if normalized(app.company) == normalized(details.company) and normalized(app.job_title) == normalized(details.job_title)]
    if not candidates:
        haystack = ' ' + normalized(headers.get('subject', '') + ' ' + full_text) + ' '
        candidates = [app for app in records if (' ' + normalized(app.company) + ' ') in haystack
            and (' ' + normalized(app.job_title) + ' ') in haystack]
    active = [app for app in candidates if not app.deleted_at]
    candidates = active or candidates
    if len(candidates) != 1:
        return None, bool(candidates)
    return candidates[0], False


def reconcile(engine, settings, account, message, *, mailbox_email=None):
    """One atomic message transaction: receipt, record, source reference and timeline."""
    headers, fresh, full_text, details, posting, at = evidence(message)
    message_id = message['id']
    reference = ('https://mail.google.com/mail/?' + urlencode({'authuser': mailbox_email}) + '#all/' + message_id
                 if mailbox_email else f'https://mail.google.com/mail/u/0/#all/{message_id}')
    with Session(engine) as session:
        receipt = session.get(MailImportReceipt, (account, message_id))
        if receipt and receipt.state != 'REVIEW':
            return None, False, False
        receipt = receipt or MailImportReceipt(account=account, message_id=message_id)
        receipt.thread_id = message.get('thread_id', '')
        receipt.subject = headers.get('subject', 'Application email')[:500]
        receipt.message_at = at
        receipt.state, receipt.reason, receipt.lifecycle_applied = 'REVIEW', 'No unique application match. Review this email.', False
        app, ambiguous = match_application(session, account, message, headers, full_text, details, posting)
        created = False
        if ambiguous:
            receipt.reason = 'Several applications match this email. Choose the correct application manually.'
        elif app and app.deleted_at:
            receipt.state, receipt.reason = 'APPLIED', 'Deleted application preserved.'
            receipt.application_id = app.id
            session.add(receipt); session.commit()
            return None, False, False
        elif app is None and details.company and details.job_title and details.kind in ('APPLICATION_CONFIRMATION', 'CV_FORWARDED') and at:
            applied = details.date_applied or at.date()
            if not details.date_applied:
                try:
                    applied = parsedate_to_datetime(headers.get('date', '')).date()
                except (ValueError, TypeError, OverflowError):
                    pass
            app = applications.create_application(session, ApplicationCreate(
                company=details.company, job_title=details.job_title, intermediary=details.intermediary,
                date_applied=applied, job_url=posting.get('job_url'),
                source=posting.get('source'), email_reference=reference),
                settings=settings, actor_type=ActorType.SYSTEM, actor_reference='gmail-sync', commit=False,
                application_id=str(uuid5(NAMESPACE_URL, f"application-tracker:gmail:{account}:{message.get('thread_id') or message_id}")))
            created = True
        changed = False
        if app and not ambiguous:
            receipt.application_id = app.id
            changes = {}
            references = (app.email_reference or '').splitlines()
            if not any(message_id.casefold() in line.casefold() for line in references):
                joined = '\n'.join([*references, reference])
                if len(joined) <= 2048:
                    changes['email_reference'] = joined
            if not app.job_url and posting.get('job_url'):
                changes['job_url'], changes['source'] = posting['job_url'], posting.get('source')
            decision = lifecycle(fresh)
            latest = session.scalar(select(func.max(MailImportReceipt.message_at)).where(
                MailImportReceipt.application_id == app.id, MailImportReceipt.lifecycle_applied.is_(True)))
            human_decision = session.scalar(select(func.max(TimelineEvent.created_at)).where(
                TimelineEvent.application_id == app.id, TimelineEvent.event_type.in_(('STATUS_CHANGED', 'OUTCOME_CHANGED')),
                TimelineEvent.actor_type != ActorType.SYSTEM))
            differs = any(getattr(app, key) != value for key, value in decision.items())
            if decision and differs and (not at or app.status == ApplicationStatus.CLOSED or latest and at <= latest or human_decision and at <= human_decision):
                receipt.reason = 'Status evidence conflicts with a newer or closed application decision. Review it manually.'
            elif not decision and details.kind not in ('APPLICATION_CONFIRMATION', 'CV_FORWARDED'):
                receipt.reason = 'No unambiguous application update found. Review this email.'
            else:
                receipt.state, receipt.reason = 'APPLIED', ''
                if decision:
                    changes.update(decision)
                    receipt.lifecycle_applied = True
            if changes:
                app = applications.update_application(session, app.id, ApplicationUpdate(**changes, expected_revision=app.revision),
                    settings=settings, actor_type=ActorType.SYSTEM, actor_reference='gmail-sync', commit=False)
                changed = True
            if decision.get('status') == 'INTERVIEW' and not app.followup_paused:
                receipt.state = 'REVIEW'
                receipt.reason = 'Interview invitation detected. Review whether existing follow-ups should be kept, paused or archived.'
            # Never replace stored email text; keep the original mailbox available for review.
            exists = session.scalar(select(TimelineEvent.id).where(TimelineEvent.application_id == app.id,
                TimelineEvent.event_metadata['gmail_message_id'].as_string() == message_id))
            if not exists:
                record_event(session, app.id, 'MANUAL', (receipt.subject[:350] + ' ' + reference)[:500],
                    actor_type=ActorType.SYSTEM, actor_reference='gmail-sync', occurred_at=at,
                    metadata={'gmail_message_id': message_id})
                changed = True
            session.add(InvalidationEvent(topic='application.updated', application_id=app.id))
        session.add(receipt)
        session.commit()
        return app.id if app else None, created, changed
