"""Offline tests for tracker field feedback: no network, mailbox probing or browser."""
import asyncio
from pathlib import Path

import pytest
from webtoolbox import Settings, WebToolbox
from webtoolbox.contacts import extract_contacts, assess_employer, extract_contact_links
from webtoolbox.core import _fit_response
from webtoolbox.frontier import contact_page_priority, prioritize_contact_links
from webtoolbox.ranking import merge_and_rank, rank_contact
import webtoolbox.core as core


def test_form_examples_remain_diagnostics_not_recommendations():
    html = '''<main><h2>Comment postuler ?</h2>
    <p>Exemple de format : nom@domaine.fr</p>
    <p>Renseignez nom.prenom@domaine.com dans le formulaire.</p>
    <p>Postulez à recrutement@real-employer.fr</p></main>'''
    found = {r["email"]: r for r in extract_contacts(html, "https://real-employer.fr/carrieres")}
    assert len(found) == 3
    for address in ("nom@domaine.fr", "nom.prenom@domaine.com"):
        assert found[address]["exclusion_reason"] == "example_or_placeholder_address"
        assert found[address]["emails"][0]["evidence"]
        assert not rank_contact(found[address])["contact_priority"]["outreach_eligible"]
    assert found["recrutement@real-employer.fr"]["purpose"] == "recruitment"


def test_press_and_marketing_localparts_are_not_recruitment():
    html = '''<main><p>globalprteam@company.fr</p><p>marketing@company.fr</p>
    <p>recrutement@company.fr</p></main>'''
    records = {r["email"]: r for r in extract_contacts(html, "https://company.fr/contact")}
    assert records["globalprteam@company.fr"]["purpose"] == "media"
    assert records["marketing@company.fr"]["purpose"] == "sales"
    assert records["recrutement@company.fr"]["purpose"] == "recruitment"


def test_policy_page_purpose_excludes_cookie_administration():
    values = extract_contacts('<p>Email : administration@company.fr</p>', "https://company.fr/cookies")
    assert values[0]["purpose"] == "privacy"
    assert values[0]["exclusion_reason"] == "not_recruitment_privacy_page"
    assert rank_contact(values[0])["contact_priority"]["category"] == "excluded"


def test_employer_collision_sector_context_remains_unconfirmed():
    candidate = extract_contacts('<p>Contact : service@atos-hydraulics.it</p>', 'https://atos-hydraulics.it/contact')[0]
    result = assess_employer(candidate, "Atos", target_sector="informatique", source_context={"sector": "hydraulics", "region": "italy"},
                             target_region="france")
    assert result["employer_match"]["state"] == "unknown"
    assert result["fit"]["sector"]["state"] == "mismatch"
    assert result["fit"]["region"]["state"] == "mismatch"
    assert rank_contact(result)["contact_priority"]["outreach_eligible"] is False


def test_region_fit_and_team_assignment_separated():
    card = extract_contacts('<div class="person"><h2>Jane Smith</h2><p class="role">Chief People Officer</p><a href="mailto:jane@edenred.fr">Email</a></div>',
                             'https://company.example/team')[0]
    out = assess_employer(card, "Edenred", target_region="France", source_context={"region": "USA"})
    ranked = rank_contact(out)
    assert ranked["contact_priority"]["category"] == "named_recruiter"
    assert ranked["contact_priority"]["outreach_eligible"] is False
    assert ranked["fit"]["vacancy_team_responsibility"] == "unknown"
    assert ranked["contact_priority"]["recommended_action"] == "verify_region_or_team_fit"


def test_country_context_cannot_prove_office_team():
    card = extract_contacts('<p>Postulez recrutement@company.fr</p>', 'https://company.fr/carrieres')[0]
    result = assess_employer(card, "Company", target_region="Toulouse", source_context={"region": "France"})
    assert result["fit"]["region"]["state"] == "country_only"
    assert result["fit"]["vacancy_team_responsibility"] == "unknown"


def test_director_of_people_is_hr_lead_not_vacancy_owner():
    html = '''<article class="person"><h3>Marie France</h3><span class="role">Chief People Officer</span></article>'''
    record = rank_contact(extract_contacts(html, "https://company.fr/team")[0])
    assert record["contact_priority"]["category"] == "named_recruiter"
    assert record["vacancy_responsibility"] == "unknown"
    assert record["email"] is None


def test_link_frontier_rejects_vendor_cookie_pages_and_collapses_locales():
    links = [
        {"url":"https://company.fr/privacy", "label":"privacy"},
        {"url":"https://vendor.fr/credits", "label":"Site by Agency"},
        {"url":"https://company.fr/fr/contact", "label":"Nous contacter"},
        {"url":"https://company.fr/en/contact", "label":"Contact us"},
        {"url":"https://company.fr/team", "label":"Our team"},
    ]
    result = prioritize_contact_links(links,"https://company.fr")
    assert len(result) == 2
    assert any(len(item["alternate_urls"]) == 1 for item in result)
    assert all("privacy" not in item["url"] for item in result)
    assert contact_page_priority("https://company.fr/cookies") < 0


def test_page_links_keep_labels_and_evidence_after_ranking():
    html = '<a href="/privacy">Privacy</a><a href="/contact">Careers contact</a>'
    links = extract_contact_links(html,"https://company.fr")
    assert len(links) == 1 and links[0]["label"] == "Careers contact"
    assert links[0]["evidence"]["source_url"] == "https://company.fr"


def test_stale_source_cannot_become_fresh_when_merged_with_new_page():
    base = extract_contacts('<p>Postulez recrutement@company.fr</p>', 'https://company.fr/recrutement')[0]
    stale = {**base, "cache_stale": True, "fetched_at": "2026-01-01T00:00:00Z"}
    fresh = {**base, "cache_stale": False, "source_url": "https://company.fr/carrieres", "fetched_at": "2026-10-01T00:00:00Z"}
    ranked = merge_and_rank([stale, fresh])[0]
    assert ranked["cache_stale"] is True
    assert ranked["contact_priority"]["outreach_eligible"] is False
    assert len(ranked["source_observations"]) == 2
    assert {x["fetched_at"] for x in ranked["source_observations"]} == {"2026-01-01T00:00:00Z", "2026-10-01T00:00:00Z"}
    assert ranked["contact_priority"]["recommended_action"] == "refresh_stale_evidence"


def test_truncation_reports_partial_complete_results_and_keeps_full_records():
    items = [{"source_url": "https://company.fr/" + "a" * 120, "email": f"user{i}@company.fr", "evidence": [{"excerpt":"x"*80}]} for i in range(6)]
    value = _fit_response({"completion":"complete", "candidates":items}, 180)
    assert value["completion"] == "partial"
    assert value["response_partial_reason"] == "output_budget"
    assert value["result_counts_before_budget"]["candidates"] == 6
    assert len(value["candidates"]) + value["truncation"]["omitted_records"] == 6
    assert all(x["email"].endswith("@company.fr") for x in value["candidates"])


@pytest.mark.asyncio
async def test_ddgs_no_results_exception_is_empty_not_upstream_error(tmp_path, monkeypatch):
    async def empty(query, count):
        raise Exception("DDGSException: No results found.")
    monkeypatch.setattr(core,"ddgs_search",empty)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        response = await web.search("Nothing exists")
    assert response["outcome"] == "empty" and response["results"] == []


@pytest.mark.asyncio
async def test_ddgs_upstream_error_remains_explicit_in_legacy_entry_points(tmp_path, monkeypatch):
    async def failed(query, count):
        raise Exception("service upstream unavailable")
    monkeypatch.setattr(core,"ddgs_search",failed)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        s = await web.search("Company recruitments")
        r = await web.research("Company recruitments")
    assert s["outcome"] == "upstream_error" and s["results"] == []
    assert r["completion"] == "unresolved"
    assert r["search_attempts"][0]["outcome"] == "upstream_error"


@pytest.mark.asyncio
async def test_contact_fallback_continues_past_job_mirror(tmp_path, monkeypatch):
    monkeypatch.setattr(core,"validate_url",lambda url, **kwargs:url)
    seen=[]
    async def search(query, count):
        seen.append(query)
        if "recrutement contact" in query:
            return [{"url":"https://mirror.net/jobs/posting/12345", "title":"Vacancy copy"}]
        return [{"url":"https://company.fr/contact", "title":"Contact équipe recrutement"}]
    async def fetch(self,url):
        if "company.fr" in url:
            return '<p>Postulez : recrutement@company.fr</p>', url
        return '<html><main>Alternance software engineer</main></html>', url
    monkeypatch.setattr(core,"ddgs_search",search)
    monkeypatch.setattr(WebToolbox,"_static_fetch",fetch)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        response = await web.research_contacts("Company", pages=1, max_tokens=10000)
    assert len(seen) >= 2
    assert response["crawl_attempts"][0]["url"] == "https://company.fr/contact"
    assert response["candidates"][0]["email"] == "recrutement@company.fr"


@pytest.mark.asyncio
async def test_frontier_expands_contact_link_within_page_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(core,"validate_url",lambda url, **kwargs:url)
    async def search(query, count):
        return [{"url":"https://company.fr/", "title":"Company website"}]
    async def fetch(self, url):
        if url.endswith("/contact"):
            return '<p>recrutement@company.fr Postulez ici</p>', url
        return '<a href="/privacy">Politique de confidentialité</a><a href="/contact">Contact recrutement</a>', url
    monkeypatch.setattr(core,"ddgs_search",search)
    monkeypatch.setattr(WebToolbox,"_static_fetch",fetch)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        response=await web.research_contacts("Company", pages=2, max_tokens=16000)
    assert len(response["crawl_attempts"]) == 2
    assert response["crawl_attempts"][1]["url"] == "https://company.fr/contact"
    assert response["candidates"][0]["email"] == "recrutement@company.fr"


def test_press_word_does_not_match_expression_and_sales_not_salesforce():
    html = '''<div class="person"><h3>Alex Doe</h3><span class="role">Salesforce developer</span>
              <p>expressions régulières</p><a href="mailto:alex@company.fr">Email</a></div>'''
    record = extract_contacts(html, "https://company.fr/team")[0]
    assert record["emails"][0]["exclusion_reason"] is None
    assert record["exclusion_reason"] is None


def test_unrecognized_geo_region_remains_unknown():
    card = extract_contacts('<p>recrutement@company.fr</p>', 'https://company.fr/contact')[0]
    result = assess_employer(card, 'Company', target_region='Toulouse', source_context={'region': 'FR-31'})
    assert result['fit']['region']['state'] == 'unknown'
