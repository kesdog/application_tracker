"""Apply one message atomically; scanning and matching live in their own modules."""
from typing import NamedTuple
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import applications
from app.activity import record_event
from app.followup_templates import current_settings
from app.mailbox_evidence import MailEvidence, mail_reference, read_evidence
from app.mailbox_matching import match_application
from app.models import ActorType, Application, ApplicationStatus, InvalidationEvent, MailImportReceipt, TimelineEvent
from app.schemas import ApplicationCreate, ApplicationUpdate


class ImportResult(NamedTuple):
    application_id: str | None = None
    created: bool = False
    changed: bool = False


def _prepare_receipt(account: str, evidence: MailEvidence, receipt: MailImportReceipt | None = None) -> MailImportReceipt:
    receipt = receipt or MailImportReceipt(account=account, message_id=evidence.message_id)
    receipt.thread_id = evidence.thread_id
    receipt.subject = evidence.headers.get('subject', 'Application email')[:500]
    receipt.message_at = evidence.message_at
    # Start conservatively; only a supported, safe decision clears review.
    receipt.state = 'REVIEW'
    receipt.reason = 'No unique application match. Review this email.'
    receipt.lifecycle_applied = False
    return receipt


def _create_from_confirmation(session: Session, settings, account: str, evidence: MailEvidence, reference: str) -> Application | None:
    details = evidence.details
    if not (evidence.is_confirmation and details.company and details.job_title and evidence.message_at):
        return None
    # Stable message identity prevents retry duplicates without merging a whole thread.
    application_id = str(uuid5(NAMESPACE_URL, f'application-tracker:gmail:{account}:{evidence.message_id}'))
    return applications.create_application(
        session, ApplicationCreate(
            company=details.company, job_title=details.job_title, intermediary=details.intermediary,
            date_applied=evidence.applied_on, job_url=evidence.posting.get('job_url'),
            source=evidence.posting.get('source'), email_reference=reference),
        settings=settings, actor_type=ActorType.SYSTEM, actor_reference='gmail-sync',
        commit=False, application_id=application_id,
    )


def _reference_changes(app: Application, evidence: MailEvidence, reference: str) -> dict:
    changes = {}
    references = (app.email_reference or '').splitlines()
    if not any(evidence.message_id.casefold() in line.casefold() for line in references):
        joined = '\n'.join([*references, reference])
        if len(joined) <= 2048:
            changes['email_reference'] = joined
    if not app.job_url and evidence.posting.get('job_url'):
        changes['job_url'] = evidence.posting['job_url']
        changes['source'] = evidence.posting.get('source')
    return changes


def _lifecycle_changes(session: Session, app: Application, evidence: MailEvidence, receipt: MailImportReceipt) -> dict:
    decision = evidence.scan.decision
    latest_mail_decision = session.scalar(select(func.max(MailImportReceipt.message_at)).where(
        MailImportReceipt.application_id == app.id, MailImportReceipt.lifecycle_applied.is_(True)))
    latest_human_decision = session.scalar(select(func.max(TimelineEvent.created_at)).where(
        TimelineEvent.application_id == app.id, TimelineEvent.event_type.in_(('STATUS_CHANGED', 'OUTCOME_CHANGED')),
        TimelineEvent.actor_type != ActorType.SYSTEM))
    differs = any(getattr(app, key) != value for key, value in decision.items())
    older_than_mail = latest_mail_decision and evidence.message_at and evidence.message_at <= latest_mail_decision
    older_than_human = latest_human_decision and evidence.message_at and evidence.message_at <= latest_human_decision
    protected = not evidence.message_at or app.status == ApplicationStatus.CLOSED or older_than_mail or older_than_human

    # Keep human/closed decisions and newer evidence authoritative. Repeating the
    # same status is harmless, but a conflicting older message needs human review.
    if decision and differs and protected:
        receipt.reason = 'Status evidence conflicts with a newer or closed application decision. Review it manually.'
        return {}
    if not decision and not evidence.is_confirmation:
        receipt.reason = 'No unambiguous application update found. Review this email.'
        return {}
    receipt.state, receipt.reason = 'APPLIED', ''
    receipt.lifecycle_applied = bool(decision)
    return decision


def _record_source(session, app, evidence: MailEvidence, receipt, reference) -> bool:
    exists = session.scalar(select(TimelineEvent.id).where(
        TimelineEvent.application_id == app.id,
        TimelineEvent.event_metadata['gmail_message_id'].as_string() == evidence.message_id))
    if exists:
        return False
    # Retain the original mail link; the timeline never replaces it with a summary.
    record_event(
        session, app.id, 'MANUAL', (receipt.subject[:350] + ' ' + reference)[:500],
        actor_type=ActorType.SYSTEM, actor_reference='gmail-sync', occurred_at=evidence.message_at,
        metadata={'gmail_message_id': evidence.message_id, 'mail_scanner': evidence.scan.scanner,
                  'mail_language': evidence.scan.language},
    )
    return True


def _update_matched_application(session, settings, app, evidence: MailEvidence, receipt, reference) -> bool:
    receipt.application_id = app.id
    # References can be saved even when a status decision still needs review.
    changes = _reference_changes(app, evidence, reference)
    changes.update(_lifecycle_changes(session, app, evidence, receipt))
    if changes:
        app = applications.update_application(
            session, app.id, ApplicationUpdate(**changes, expected_revision=app.revision),
            settings=settings, actor_type=ActorType.SYSTEM, actor_reference='gmail-sync', commit=False,
        )
    if evidence.scan.decision.get('status') == 'INTERVIEW' and not app.followup_paused:
        # An invitation does not choose whether the user's follow-ups should stop.
        receipt.state = 'REVIEW'
        receipt.reason = 'Interview invitation detected. Review whether existing follow-ups should be kept, paused or archived.'
    source_added = _record_source(session, app, evidence, receipt, reference)
    session.add(InvalidationEvent(topic='application.updated', application_id=app.id))
    return bool(changes) or source_added


def reconcile_evidence(engine, settings, account, evidence: MailEvidence, *, mailbox_email=None) -> ImportResult:
    """Commit application, receipt and source history as one message transaction."""
    reference = mail_reference(evidence.message_id, mailbox_email)
    with Session(engine) as session:
        receipt = session.get(MailImportReceipt, (account, evidence.message_id))
        if receipt and receipt.state != 'REVIEW':
            return ImportResult()
        receipt = _prepare_receipt(account, evidence, receipt)
        cutoff = date.fromisoformat(current_settings(session, settings)['mail_sync_not_before'])
        applied_on = date.fromisoformat(evidence.applied_on) if isinstance(evidence.applied_on, str) else evidence.applied_on
        # Search timestamps describe delivery, not the application itself. Check
        # the extracted application date before creating or updating any record.
        if applied_on is not None and applied_on < cutoff:
            receipt.state, receipt.reason = 'IGNORED', f'Application predates mail boundary {cutoff.isoformat()}.'
            session.add(receipt)
            session.commit()
            return ImportResult()
        match = match_application(session, account, evidence, not_before=cutoff)
        app, created, changed = match.application, False, False
        if app and app.date_applied < cutoff:
            receipt.state, receipt.reason = 'IGNORED', f'Application predates mail boundary {cutoff.isoformat()}.'
            receipt.application_id = app.id
            session.add(receipt)
            session.commit()
            return ImportResult()
        if match.ambiguous:
            receipt.reason = 'Several applications match this email. Choose the correct application manually.'
        elif app and app.deleted_at:
            receipt.state, receipt.reason = 'APPLIED', 'Deleted application preserved.'
            receipt.application_id = app.id
            session.add(receipt)
            session.commit()
            return ImportResult()
        else:
            if app is None:
                app = _create_from_confirmation(session, settings, account, evidence, reference)
                created = app is not None
            if app:
                changed = _update_matched_application(session, settings, app, evidence, receipt, reference)
        session.add(receipt)
        # A failure rolls back the receipt too, so a retry cannot skip a partial write.
        session.commit()
        return ImportResult(app.id if app else None, created, changed)


def reconcile(engine, settings, account, message, *, mailbox_email=None) -> ImportResult:
    """Convenience entry point for a raw message; scan workers reuse parsed evidence."""
    return reconcile_evidence(engine, settings, account, read_evidence(message), mailbox_email=mailbox_email)
