import pytest

from app.mail_scanners import scan_email
from app.mail_scanners.languages import applied_date, normalized, search_terms


@pytest.mark.parametrize(('provider', 'sender', 'language', 'body'), [
    ('indeed', 'apply@indeed.com', 'en', 'Application submitted Engineer Acme - Paris The following items were sent to Acme. Good luck!'),
    ('indeed', 'apply@indeed.fr', 'fr', 'Candidature envoyée Engineer Acme - Paris Les éléments suivants ont été envoyés à Acme. Bonne chance !'),
    ('linkedin', 'jobs-noreply@linkedin.com', 'en', 'Your application was sent to Acme Engineer Acme · Paris Applied on September 24, 2026'),
    ('linkedin', 'jobs-noreply@linkedin.com', 'fr', 'Votre candidature a été envoyée à Acme Engineer Acme · Paris Candidature envoyée le 24 septembre 2026'),
    ('freework', 'contact@free-work.com', 'en', 'Your application for Engineer at Acme has been successfully sent.'),
    ('freework', 'contact@free-work.com', 'fr', 'Votre candidature au poste Engineer chez Acme a bien été envoyée.'),
    ('generic', 'ats@unknown.example', 'en', 'Thank you for applying for Engineer at Acme.'),
    ('generic', 'ats@unknown.example', 'fr', 'Merci pour votre candidature pour le poste de Engineer chez Acme.'),
])
def test_provider_and_language_are_independent(provider, sender, language, body):
    result = scan_email(body, headers={'From': sender})
    assert (result.scanner, result.language) == (provider, language)
    assert (result.details.company, result.details.job_title, result.details.kind) == ('Acme', 'Engineer', 'APPLICATION_CONFIRMATION')
    assert result.decision == {}
    if provider == 'linkedin':
        assert result.details.date_applied == '2026-09-24'


@pytest.mark.parametrize('sender', ['jobs@linkedin.com', 'apply@indeed.com', 'contact@free-work.com', 'ats@example.test'])
@pytest.mark.parametrize(('text', 'status'), [
    ('Your application was unsuccessful.', 'CLOSED'),
    ('Votre candidature n’a pas été retenue.', 'CLOSED'),
    ('We invite you to an interview.', 'INTERVIEW'),
    ('Nous vous invitons à un entretien.', 'INTERVIEW'),
])
def test_all_scanners_share_explicit_multilingual_lifecycle_rules(sender, text, status):
    result = scan_email(text, headers={'from': sender})
    assert result.decision['status'] == status


def test_unknown_provider_template_uses_generic_fallback_without_using_sender_as_employer():
    result = scan_email('Thank you for applying for Developer at Example.', headers={'from': 'noreply@indeed.com'})
    assert result.scanner == 'generic' and result.details.company == 'Example'
    spoofed = scan_email('New job offers for you.', headers={'from': 'jobs@linkedin.com.evil.test'})
    assert spoofed.scanner == 'generic' and spoofed.details.kind == 'UNRECOGNIZED'


def test_freework_alerts_and_unknown_languages_do_not_become_applications():
    result = scan_email('<p>Latest Engineer jobs at Acme. Apply now.</p><a href="https://www.free-work.com/fr/tech-it/offre/123">Engineer</a>',
                        headers={'from': 'contact@free-work.com'})
    assert result.scanner == 'freework' and result.details.company is None
    assert result.details.kind == 'UNRECOGNIZED' and not result.decision
    unknown = scan_email('Vielen Dank für Ihre Nachricht.', headers={'from': 'jobs@linkedin.com'})
    assert unknown.details.kind == 'UNRECOGNIZED' and unknown.language is None


def test_freework_requires_a_unique_specific_posting_and_ignores_other_domains():
    body = 'Votre candidature au poste Engineer chez Acme a bien été envoyée.'
    link = 'https://www.free-work.com/fr/tech-it/offre/123'
    result = scan_email(body + f'<a href="{link}">Voir l’offre</a>', headers={'from': 'contact@free-work.com'})
    assert result.details.posting['job_url'] == link and result.details.posting['source'] == 'FREEWORK'
    ambiguous = scan_email(body + f'<a href="{link}">Role</a><a href="{link}4">Other role</a>', headers={'from': 'contact@free-work.com'})
    assert ambiguous.details.posting['job_url'] is None


def test_quoted_decisions_and_conflicting_current_decisions_are_not_applied():
    quoted = scan_email('<p>Thanks for your message.</p><blockquote>Your application was unsuccessful.</blockquote>')
    assert quoted.decision == {}
    mixed = scan_email('Thank you for applying for Engineer at Acme. Your application was unsuccessful. We invite you to an interview.')
    assert mixed.decision == {} and mixed.details.kind == 'APPLICATION_UPDATE'


def test_localized_dates_do_not_depend_on_the_process_locale_or_ui_locale():
    assert applied_date('Applied on February 29, 2024') == '2024-02-29'
    assert applied_date('Candidature envoyée le 29 février 2024') == '2024-02-29'
    assert applied_date('Candidature envoyée le 31 février 2026') is None
    assert {'application', 'interview', 'candidature', 'entretien'} <= set(search_terms())


def test_language_normalization_preserves_non_latin_scripts_for_future_packs():
    assert normalized('CANDIDATURE n’a pas été retenue.') == 'candidature n a pas ete retenue'
    assert normalized('応募ありがとうございます。') == '応募ありがとうございます'
