from datetime import datetime

import pytest

from app.mailbox_evidence import read_evidence


def message(content, headers=(), **extra):
    return {'id': 'abc1', 'thread_id': 'thread', 'content': content,
            'headers': [{'name': name, 'value': value} for name, value in headers], **extra}


def test_quoted_history_can_identify_a_record_but_cannot_supply_a_status_decision():
    evidence = read_evidence(message('<p>Thank you for replying.</p><blockquote>Engineer at Example. Your application was unsuccessful.</blockquote>'))
    assert 'Engineer at Example' in evidence.full_text
    assert 'unsuccessful' not in evidence.current_text
    assert not evidence.scan.decision and not evidence.actionable


def test_application_date_keeps_the_sender_calendar_day_while_history_uses_utc():
    evidence = read_evidence(message('Thank you for applying for Engineer at Example.',
                                    [('Date', '01 Oct 2026 23:30:00 -0400')]))
    assert evidence.message_at == datetime(2026, 10, 2, 3, 30)
    assert evidence.applied_on.isoformat() == '2026-10-01'
    assert evidence.is_confirmation and evidence.actionable


@pytest.mark.parametrize(('internal_date', 'expected'), [(1790841600000, datetime(2026, 10, 1, 8)), (None, None), ('invalid', None)])
def test_missing_sender_dates_use_delivery_time_or_remain_unknown(internal_date, expected):
    evidence = read_evidence(message('Unknown template.', internal_date=internal_date))
    assert evidence.message_at == expected
    assert evidence.applied_on == (expected.date() if expected else None)
