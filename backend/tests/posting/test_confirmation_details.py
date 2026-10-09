from app.confirmation_details import extract_confirmation_details
from app.confirmation_links import extract_confirmation_link


def test_reads_employer_and_role_from_body_not_sender_brand_or_footer():
    details = extract_confirmation_details('<p>Thank you for applying for <b>C# .NET Engineer</b> at <b>Acme</b>.</p><p>Sent by Recruiter ATS</p>')
    assert (details.job_title, details.company, details.kind) == ('C# .NET Engineer', 'Acme', 'APPLICATION_CONFIRMATION')
    assert details.intermediary is None and details.matched_text
    french = extract_confirmation_details('Nous vous remercions pour votre candidature pour le poste de Développeur chez Exemple. Nous reviendrons vers vous.')
    assert (french.job_title, french.company) == ('Développeur', 'Exemple')


def test_iscod_forwarding_is_distinct_from_employer_and_not_an_offer():
    details = extract_confirmation_details("Votre CV a été envoyé à l’entreprise A3COM - IT qui recherche un alternant ! Équipe ISCOD. https://www.iscod.fr/offres-emploi-en-alternance/alternance-developpeur-c-net-abc123")
    assert (details.company, details.intermediary, details.kind) == ('A3COM', 'ISCOD', 'CV_FORWARDED')
    assert details.job_title is None
    assert details.posting['job_url'].endswith('abc123')


def test_indeed_iscod_advertiser_does_not_disclose_actual_employer():
    details = extract_confirmation_details('Candidature envoyée Alternance Développeur Full Stack NODE (F/H) ISCOD - Paris Paris 8 avis Les éléments suivants ont été envoyés à ISCOD. Bonne chance !')
    assert details.company is None and details.intermediary == 'ISCOD'
    assert details.job_title == 'Alternance Développeur Full Stack NODE (F/H)'


def test_linkedin_preamble_and_related_roles_do_not_replace_actual_role_or_date():
    details = extract_confirmation_details('Your application was sent to Acme \u034f Your application was sent to Acme Software Engineer Acme · Paris Applied on September 24, 2026 View similar jobs Full Stack Developer Other Corp · Lyon')
    assert (details.company, details.job_title, details.date_applied) == ('Acme', 'Software Engineer', '2026-09-24')
    display = extract_confirmation_details('<h2>Your application was sent to EEMI - School</h2><p>Developpeur Web EEMI · Lyon Applied on September 24, 2026</p><a href="https://linkedin.com/comm/jobs/view/123/">Developpeur Web</a><a href="https://linkedin.com/comm/jobs/view/456/">Unrelated role</a>')
    assert (display.company, display.job_title) == ('EEMI - School', 'Developpeur Web')


def test_rejection_and_unnamed_employer_are_not_new_application_evidence():
    details = extract_confirmation_details("Nous vous remercions pour votre candidature pour le poste Développeur chez Acme.Malheureusement, votre candidature n'a pas été retenue.")
    assert details.company == 'Acme' and details.job_title == 'Développeur'
    assert details.kind == 'APPLICATION_UPDATE'
    assert extract_confirmation_details('Merci pour votre candidature pour le poste de Développeur chez notre entreprise.').company is None


def test_recovers_slugged_linkedin_and_labeled_employer_posting_but_not_company_page():
    assert extract_confirmation_link('https://fr.linkedin.com/jobs/view/full-stack-engineer-4463232717/').job_url == 'https://www.linkedin.com/jobs/view/4463232717/'
    assert extract_confirmation_link('<a href="https://employer.test/jobs/123">View job</a>').job_url == 'https://employer.test/jobs/123'
    assert extract_confirmation_link('<a href="https://employer.test/jobs/">View job</a>').job_url is None
