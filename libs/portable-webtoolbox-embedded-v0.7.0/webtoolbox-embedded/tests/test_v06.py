"""v0.6 offline source-backed regression cases; no live web/Chromium needed."""
from pathlib import Path
import json

import pytest

from webtoolbox import WebToolbox, Settings, EmployerContext, load_profile
from webtoolbox.contacts import extract_contacts, assess_employer, extract_contact_links
from webtoolbox.frontier import contact_page_priority
from webtoolbox.identity import site_identity, legal_name_matches
from webtoolbox.ranking import rank_contact
import webtoolbox.core as core

FIX = Path(__file__).parent / "fixtures"


def test_centurion_confidential_vacancy_has_published_application_mailbox():
    page = (FIX / "centurion-confidential-vacancies.html").read_text()
    result = extract_contacts(page, "https://centurion-search.fr/carrieres")
    assert len(result) == 1
    entry = result[0]
    assert entry["email"] == "candidature@centurion-search.fr"
    assert entry["purpose"] == "recruitment"
    assert entry["exclusion_reason"] is None
    assert entry["emails"][0]["evidence"]


def test_privacy_policy_remains_excluded_and_placeholder_is_ignored():
    html = '<p>Pour exercer vos droits, contactez dpo@firm.fr</p><p>Format nom@domaine.fr</p>'
    output = extract_contacts(html, "https://firm.fr/politique-de-confidentialite")
    assert {v["purpose"] for v in output} == {"privacy", "example"}
    assert all(v["exclusion_reason"] for v in output)


def test_employer_domain_requires_explicit_evidence_and_excludes_lookalikes():
    ctx = EmployerContext(company="Atos", domain="atos.net", status="confirmed", evidence_source="user_confirmed")
    assert ctx.assess("https://atos.net/carrieres")["state"] == "confirmed"
    assert ctx.assess("https://atos.com/")["state"] == "unknown"
    assert not ctx.allows_crawl("https://evil-atos.net/jobs")
    assert ctx.allows_crawl("https://jobs.atos.net/role")
    assert EmployerContext(company="Atos", domain="atos.net", status="provisional").assess("https://atos.net/")["state"] == "provisional"
    with pytest.raises(ValueError):
        EmployerContext(company="Atos", domain="atos.net", status="confirmed")


def test_ats_site_is_not_an_employer_identity_confirmation():
    ctx = EmployerContext(company="Atos", domain="atos.net", status="confirmed", evidence_source="job_posting",
                          ats_domains=("ats.example.net",))
    assert ctx.allows_crawl("https://ats.example.net/job/abc")
    assert ctx.assess("https://ats.example.net/job/abc")["state"] == "provisional"


def test_site_owner_metadata_warns_on_unknown_legal_name_not_vendor_credit():
    html = (FIX / "atos-hydraulics.html").read_text()
    owner = site_identity(html, "https://atos.com/")
    assert owner["legal_name"] == "Atos Hydraulics SRL"
    ctx = EmployerContext(company="Atos", domain="atos.com", status="confirmed", evidence_source="user_confirmed")
    record = extract_contacts(html, "https://atos.com/")[0]
    assessment = assess_employer(record, "Atos", employer_context=ctx, source_context={"site_identity": owner})
    assert assessment["employer_match"]["state"] == "provisional"
    assert assessment["identity_warning"] == "unresolved_publisher_legal_name"
    assert not rank_contact(assessment)["contact_priority"]["outreach_eligible"]
    assert legal_name_matches("Atos SE", EmployerContext(company="Atos"))
    assert not legal_name_matches("Unrelated Web Agency", EmployerContext(company="Atos"))


def test_custom_keyword_profile_can_change_purposes_titles_and_crawl_frontier(tmp_path):
    overrides = {"contact_recruitment": ["talentpool", "candidat"],
                 "recruiter_titles": ["candidate relationship manager"],
                 "page_positive": ["équipe", "contact", "talentpool"],
                 "page_negative": ["costly-ads", "cookies"],
                 "keywords": {"required": ["alternance"], "preferred": {"python": 10},
                              "excluded": ["stage"], "synonyms": {"alternance": ["apprentissage"]}}}
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(overrides), encoding="utf-8")
    profile = load_profile(path)
    assert profile.score_text("Apprentissage Python")["eligible"]
    assert profile.score_text("stage apprentissage")["eligible"] is False
    assert profile.score_text("Python")["missing_required"] == ["alternance"]
    contact = extract_contacts('<div class="person"><h3>Marc A</h3><p class="role">Candidate relationship manager</p></div>',
                               'https://company.fr/team')
    assert rank_contact(contact[0], keyword_profile=profile)["contact_priority"]["category"] == "named_recruiter"
    assert contact_page_priority("https://company.fr/costly-ads", keyword_profile=profile) < 0
    assert contact_page_priority("https://company.fr/talentpool", keyword_profile=profile) > 0


def test_unknown_profile_key_rejected():
    with pytest.raises(ValueError):
        load_profile({"magical_new_operator": "foo"})


def test_unrelated_links_are_not_in_selected_frontier():
    html = (FIX / "atos-it.html").read_text()
    links = extract_contact_links(html, "https://atos.net/")
    assert [x["url"] for x in links] == ["https://atos.net/equipe"]


@pytest.mark.asyncio
async def test_v06_avoids_atos_collision_and_page_ads(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kwargs: url)
    touched = []

    async def provider(query, count):
        return [{"url": "https://atos.com/", "title": "Atos hydraulics", "snippet": "Hydraulic equipment"},
                {"url": "https://atos.net/pricing", "title": "Recruitment advertising prices", "snippet": ""},
                {"url": "https://atos.net/", "title": "Atos IT", "snippet": "software company"}]

    async def fetch(self, url):
        touched.append(url)
        if url.endswith("/equipe"):
            return '<p>Pour candidater : recrutement@atos.net</p>', url
        return (FIX / "atos-it.html").read_text(), url

    monkeypatch.setattr(core, "ddgs_search", provider)
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    ctx = EmployerContext(company="Atos", domain="atos.net", status="confirmed", evidence_source="user_confirmed")
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        result = await web.research_contacts("Atos", employer_context=ctx, pages=2, max_tokens=18000)
    assert result["recommended_count"] >= 1
    assert len(result["crawl_attempts"]) == 2
    assert "https://atos.com/" not in touched
    assert "https://atos.net/pricing" not in touched
    assert "https://atos.net/equipe" in touched
    assert any(x["url"] == "https://atos.com/" for x in result["excluded_domains"])


@pytest.mark.asyncio
async def test_official_domain_hint_does_not_silently_verify_contacts(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kwargs: url)
    async def provider(query, count):
        return [{"url": "https://company.fr/carrieres", "title": "Recrutement"}]
    async def fetch(self, url):
        return '<p>Envoyez votre candidature à recrutement@company.fr</p>', url
    monkeypatch.setattr(core, "ddgs_search", provider)
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        result = await web.research_contacts("Company", official_domain="company.fr", pages=1, max_tokens=15000)
    assert result["employer_context"]["status"] == "provisional"
    assert result["recommended_count"] == 0
    assert len(result["candidates"]) >= 1
    assert result["candidates"][0]["contact_priority"]["recommended_action"] == "verify_employer_identity"


@pytest.mark.asyncio
async def test_empty_search_seeded_homepage_can_find_contact_page(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kwargs: url)
    touched = []
    async def provider(query, count):
        return []
    async def fetch(self, url):
        touched.append(url)
        return ('<a href="/contact">Contact recrutement</a>' if url.endswith("/") else
                '<p>Postulez à candidature@company.fr</p>'), url
    monkeypatch.setattr(core, "ddgs_search", provider)
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    ctx = EmployerContext(company="Company", domain="company.fr", status="confirmed", evidence_source="application_confirmation")
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        response = await web.research_contacts("Company", employer_context=ctx, pages=2, max_tokens=18000)
    assert touched == ["https://company.fr/", "https://company.fr/contact"]
    assert response["recommended_count"] == 1
    assert response["search_attempts"] and all(a["outcome"] == "empty" for a in response["search_attempts"])


@pytest.mark.asyncio
async def test_profile_changes_search_without_invalidating_raw_search_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kwargs: url)
    calls=[]
    async def provider(query, count):
        calls.append(query)
        return [{"url":"https://jobs.fr/123", "title":"Java alternance", "snippet":""},
                {"url":"https://jobs.fr/456", "title":"Python apprentissage", "snippet":""}]
    monkeypatch.setattr(core, "ddgs_search", provider)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        a = await web.search("software", keyword_profile={"keywords":{"preferred":{"python":5}}}, max_tokens=3000)
        b = await web.search("software", keyword_profile={"keywords":{"preferred":{"java":5}}}, max_tokens=3000)
    assert len(calls) == 1
    assert "Python" in a["results"][0]["title"]
    assert "Java" in b["results"][0]["title"]
    assert b["cache_state"]["cached"]


def test_status_keywords_are_customizable_without_guessing_live():
    from webtoolbox.job_postings import parse_job_page, assess_status
    url = "https://company.fr/offre/def56789"
    html = '<html><body><main><h1>Alternance développeur</h1><p>Offre suspendue temporairement</p></main></body></html>'
    original = parse_job_page(html, url)
    assert assess_status(original, url)[0] == "UNKNOWN"
    profile = load_profile({"job_closed": ["offre suspendue"]})
    customized = parse_job_page(html, url, keyword_profile=profile)
    assert assess_status(customized, url)[0] == "CLOSED"


def test_application_action_words_can_be_edited():
    from webtoolbox.job_postings import parse_job_page
    url = "https://company.fr/offre/def56789"
    html = '<html><body><h1>Un poste</h1><a href="/start">Envoyer mon dossier</a></body></html>'
    normal = parse_job_page(html, url)
    custom = parse_job_page(html, url, keyword_profile=load_profile({"job_apply": ["envoyer mon dossier"]}))
    assert not normal["application_links"]
    assert custom["application_links"][0]["url"] == "https://company.fr/start"


@pytest.mark.asyncio
async def test_status_cache_recomputes_with_a_different_keyword_profile(tmp_path, monkeypatch):
    from webtoolbox.job_postings import platform_of
    monkeypatch.setattr(core, "validate_url", lambda url, **kwargs: url)
    url = "https://company.fr/offre/def56789"
    html = '<html><body><main><h1>Alternance développeur</h1><p>Offre suspendue temporairement</p></main></body></html>'
    calls = []
    async def fetch(self, url):
        calls.append(url)
        return html, url
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        baseline = await web.check_job_status(url)
        custom = await web.check_job_status(url, keyword_profile={"job_closed": ["offre suspendue"]})
        again = await web.check_job_status(url, keyword_profile={"job_closed": ["offre suspendue"]})
    assert baseline["status"] == "UNKNOWN"
    assert custom["status"] == "CLOSED"
    assert again["status"] == "CLOSED" and again["cached"]
    assert len(calls) == 2


def test_default_keywords_can_be_replaced_not_just_extended():
    from webtoolbox.ranking import rank_contact
    html = '<div class="person"><h3>Jeanne Petit</h3><span class="role">Chief People Officer</span></div>'
    card = extract_contacts(html, 'https://company.fr/team')[0]
    assert rank_contact(card)["contact_priority"]["category"] == "named_recruiter"
    assert rank_contact(card, keyword_profile=load_profile({"recruiter_titles": ["hr king"]}))["contact_priority"]["category"] == "named_other_contact"


def test_custom_query_templates_expand_within_bounded_ladder():
    profile = load_profile({"contact_queries": ["{company} {role} RH", "site:{domain} contact"],
                            "job_queries": ["{company} {title} {location}"]})
    assert profile.queries("contact_queries", company="Company", role="Dev", domain="") == ["Company Dev RH"]
    assert profile.queries("contact_queries", company="Company", role="Dev", domain="company.fr") == ["Company Dev RH", "site:company.fr contact"]
    assert profile.queries("job_queries", company="Company", title="Python", location="Toulouse") == ["Company Python Toulouse"]


def test_custom_confidential_vacancy_phrases_are_recruitment_not_privacy():
    from webtoolbox.contacts import purpose_for
    profile = load_profile({"vacancy_confidentiality": ["missions sous embargo"]})
    assert purpose_for("Missions sous embargo", profile=profile) == ("recruitment", None)
    assert purpose_for("politique de confidentialité et RGPD", profile=profile)[0] == "privacy"
