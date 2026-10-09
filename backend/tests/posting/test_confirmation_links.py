from app.confirmation_links import extract_confirmation_link


def test_extracts_and_canonicalizes_linkedin_job_link_from_confirmation_html():
    result = extract_confirmation_link(
        'Full Stack Engineer <a href="linkedin.com/comm/jobs/view/4390679517/?trackingId=abc&amp;trk=applied_jobs">View job</a>'
    )
    assert result.job_url == "https://www.linkedin.com/jobs/view/4390679517/"
    assert result.source == "LINKEDIN"
    assert result.reason == "Found a LinkedIn job posting link in the confirmation email"


def test_extracts_indeed_job_key_and_keeps_company_confirmation_as_non_posting_evidence():
    direct = extract_confirmation_link('https://fr.indeed.com/pagead/clk?jk=529293da834e1ec8&amp;from=confirm')
    assert direct.job_url == "https://fr.indeed.com/viewjob?jk=529293da834e1ec8"
    assert direct.source == "INDEED"

    company = extract_confirmation_link("https://fr.indeed.com/cmp/Dymension-1?campaignid=IAconfirm")
    assert company.job_url is None
    assert company.source == "INDEED"
    assert company.confirmation_url == "https://fr.indeed.com/cmp/Dymension-1?campaignid=IAconfirm"


def test_returns_an_empty_result_when_no_supported_board_link_is_present():
    result = extract_confirmation_link("Your application was received. https://example.com/jobs/1")
    assert result.job_url is None
    assert result.source is None
