"""Persistent, explicit human decisions for ambiguous mailbox imports."""
import hashlib
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from app import applications
from app.activity import record_audit, record_event
from app.models import FollowUp, FollowUpStatus, MailImportReceipt, utc_now
from app.schemas import ApplicationCreate, ApplicationUpdate


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['ignore', 'link', 'create']
    application_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    application: ApplicationCreate | None = None
    employer_reply: bool = False
    followups: Literal['keep', 'pause', 'archive'] = 'keep'


def identity(google):
    email = google.status().get('email')
    if not email:
        raise applications.InvalidApplication('Connect the matching Google account to review its imported emails.')
    return hashlib.sha256(email.casefold().encode()).hexdigest(), email


def review_page(session, google, page=1, page_size=20):
    account, email = identity(google)
    query = select(MailImportReceipt).where(MailImportReceipt.account == account, MailImportReceipt.state == 'REVIEW')
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    return {'total': total, 'page': page, 'page_size': page_size, 'items': [
        {'message_id': item.message_id, 'subject': item.subject, 'reason': item.reason,
         'application_id': item.application_id, 'message_at': item.message_at,
         'url': 'https://mail.google.com/mail/?' + urlencode({'authuser': email}) + '#all/' + item.message_id}
        for item in session.scalars(query.order_by(MailImportReceipt.message_at.desc(), MailImportReceipt.message_id)
                                    .offset((page - 1) * page_size).limit(page_size))]}


def decide(session, google, settings, message_id, data):
    account, email = identity(google)
    session.execute(text('BEGIN IMMEDIATE'))
    receipt = session.get(MailImportReceipt, (account, message_id))
    if receipt is None:
        raise applications.ApplicationNotFound('Review email not found for this Google account')
    if receipt.state != 'REVIEW':
        raise applications.InvalidApplication('This email has already been reviewed. Refresh the review list.')
    if data.action == 'ignore':
        receipt.state, receipt.reason = 'IGNORED', 'Dismissed after human review'
    else:
        if data.action == 'create':
            if data.application is None:
                raise applications.InvalidApplication('Provide the reviewed application details.')
            parent = applications.create_application(session, data.application, settings=settings, commit=False)
        else:
            parent = applications.get_application(session, data.application_id or '')
            if data.expected_revision != parent.revision:
                raise applications.ApplicationRevisionConflict(parent, {})
        reference = 'https://mail.google.com/mail/?' + urlencode({'authuser': email}) + '#all/' + message_id
        refs = (parent.email_reference or '').splitlines()
        changes = {}
        if reference not in refs:
            joined = '\n'.join([*refs, reference])
            if len(joined) > 2048:
                raise applications.InvalidApplication('This application has reached its email-reference limit. Review its existing references before linking another email.')
            changes['email_reference'] = joined
        if data.followups == 'pause':
            changes['followup_paused'] = True
        if changes:
            applications.update_application(session, parent.id, ApplicationUpdate(**changes, expected_revision=parent.revision), settings=settings, commit=False)
        if data.followups == 'archive':
            for item in session.scalars(select(FollowUp).where(FollowUp.application_id == parent.id,
                    FollowUp.status != FollowUpStatus.SENT, FollowUp.archived_at.is_(None))):
                item.archived_at = utc_now()
                item.revision += 1
                item.approved_revision = None
                record_audit(session, parent.id, 'FOLLOWUP', item.id, 'UPDATE', previous={'archived_at': None}, new={'archived_at': item.archived_at})
        if data.employer_reply:
            record_event(session, parent.id, 'EMPLOYER_REPLY_RECORDED', 'Employer reply confirmed during email review',
                         occurred_at=receipt.message_at, metadata={'gmail_message_id': message_id})
        record_event(session, parent.id, 'MAIL_REVIEWED', 'Email linked after human review', metadata={'gmail_message_id': message_id})
        receipt.state, receipt.application_id, receipt.reason = 'APPLIED', parent.id, ''
    session.commit()
    return {'state': receipt.state, 'application_id': receipt.application_id}
