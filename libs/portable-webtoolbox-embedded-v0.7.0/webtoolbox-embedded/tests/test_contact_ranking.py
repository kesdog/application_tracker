"""Regression tests for recipient ranking, vacancy evidence and safe dedup."""

import json
from pathlib import Path

import pytest

from webtoolbox import WebToolbox, Settings
from webtoolbox.contacts import assess_employer, extract_contacts
from webtoolbox.ranking import merge_and_rank, rank_contact, shortlist_summary
import webtoolbox.core as core

FIX = Path(__file__).parent / "fixtures"
JOB = "https://jobs.example.org/alternance/42"
TEAM = "https://www.example.org/team"


def test_explicit_vacancy_contact_ranked_above_named_recruiter_and_mailbox():
    job = extract_contacts((FIX / "vacancy-contact.html").read_text(), JOB, vacancy_url=JOB)
    team = extract_contacts((FIX / "team-contact.html").read_text(), TEAM, vacancy_url=JOB)
    ranked = merge_and_rank([assess_employer(c, "Example", known_domains=("example.org",))
                             for c in job + team])
    categories = [c["contact_priority"]["category"] for c in ranked]
    assert categories[:3] == ["vacancy_specific_contact", "named_recruiter", "recruitment_mailbox"]
    top = ranked[0]
    assert top["name"] == "Marie Petit" and top["email"] == "marie.petit@example.org"
    assert top["vacancy_responsibility"] == "published_for_vacancy"
    assert top["vacancy_evidence"][0]["method"] == "explicit_vacancy_contact"
    assert top["contact_priority"]["recommended_action"] == "review_before_follow_up"
    assert top["profile_urls"][0]["url"].endswith("/marie-petit/")
    assert ranked[1]["name"] == "Alex Martin" and ranked[1]["email"] is None
    assert ranked[1]["contact_priority"]["recommended_action"] == "find_contact_method"
    assert ranked[2]["contact_priority"]["outreach_eligible"]
    assert any(c["email"] == "contact@example.org" and
               c["contact_priority"]["category"] == "general_company_mailbox" for c in ranked)
    assert any(c["email"] == "presse@example.org" and
               c["contact_priority"]["category"] == "excluded" for c in ranked)
    assert sum(1 for c in ranked if c["email"] == "contact@example.org") == 1
    assert len(next(c for c in ranked if c["email"] == "contact@example.org")["source_urls"]) == 2


def test_vacancy_assertion_requires_both_local_cue_and_supplied_match():
    page = (FIX / "vacancy-contact.html").read_text()
    no_job = extract_contacts(page, JOB)
    wrong_job = extract_contacts(page, JOB, vacancy_url="https://jobs.example.org/alternance/99")
    matched = extract_contacts(page, JOB, vacancy_reference="42")
    assert next(c for c in no_job if c["name"] == "Marie Petit")["vacancy_responsibility"] == "unknown"
    assert next(c for c in wrong_job if c["name"] == "Marie Petit")["vacancy_responsibility"] == "unknown"
    # A reference found only in the URL is insufficient: it must be in the contact card.
    assert next(c for c in matched if c["name"] == "Marie Petit")["vacancy_responsibility"] == "unknown"
    assert all(c["vacancy_responsibility"] == "unknown" for c in no_job if c["email"] == "contact@example.org")


def test_conflicting_company_identity_disqualifies_even_published_recruiter():
    contacts = extract_contacts((FIX / "vacancy-contact.html").read_text(), JOB, vacancy_url=JOB)
    marie = next(c for c in contacts if c["name"] == "Marie Petit")
    conflicting = rank_contact(assess_employer(marie, "Example", conflicting_names=("Example",)))
    assert conflicting["contact_priority"]["category"] == "excluded"
    assert conflicting["contact_priority"]["outreach_eligible"] is False
    assert conflicting["vacancy_responsibility"] == "published_for_vacancy"  # Evidence survives exclusion.


def test_two_emails_on_one_card_do_not_choose_arbitrary_recipient():
    html = '''<div class="person"><h3 class="name">Zoe Martin</h3>
    <p class="role">Recruiter</p><a href="mailto:zoe@example.org">Zoe</a>
    <a href="mailto:team@example.org">Recruitment</a></div>'''
    candidate = rank_contact(extract_contacts(html, TEAM)[0])
    assert candidate["email"] is None
    assert len(candidate["emails"]) == 2
    assert candidate["contact_priority"]["outreach_eligible"] is False
    assert candidate["contact_priority"]["recommended_action"] == "verify_recipient"


def test_named_person_never_claims_unscoped_generic_mailbox():
    ranked = merge_and_rank(extract_contacts((FIX / "team-contact.html").read_text(), TEAM))
    person = next(c for c in ranked if c["name"] == "Alex Martin")
    generic = next(c for c in ranked if c["email"] == "contact@example.org")
    assert person["email"] is None and generic["name"] is None
    assert person["vacancy_responsibility"] == "unknown"
    assert generic["contact_priority"]["recommended_action"] == "verify_recruitment_purpose"


@pytest.mark.asyncio
async def test_embedded_research_contacts_ranks_and_deduplicates_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kwargs: url)

    async def provider(query, count):
        return [{"url": JOB, "title": "Alternance Full Stack", "snippet": ""},
                {"url": TEAM, "title": "Our recruitment team", "snippet": ""}]

    async def fetch(self, url):
        return (FIX / ("vacancy-contact.html" if url == JOB else "team-contact.html")).read_text(), url

    monkeypatch.setattr(core, "ddgs_search", provider)
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        response = await web.research_contacts("Example", official_domain="example.org",
                                                   employer_context={"company":"Example", "domain":"example.org",
                                                       "status":"confirmed", "evidence_source":"user_confirmed"},
                                                   vacancy_url=JOB,
                                               max_tokens=18000, pages=2)
    # One unvisited homepage remains after the page budget: partial, not failed.
    assert response["completion"] == "partial"
    assert response["page_budget_exhausted"] is True
    assert len(response["crawl_attempts"]) == 2
    assert response["candidates"][0]["name"] == "Marie Petit"
    assert response["contact_categories"]["vacancy_specific_contact"] == 1
    assert response["contact_categories"]["named_recruiter"] == 1
    assert response["recommended_count"] == 2  # Named contact and recruitment mailbox.
    generic = [c for c in response["candidates"] if c["email"] == "contact@example.org"]
    assert len(generic) == 1 and len(generic[0]["source_urls"]) == 2
    assert not any(c["email"] == "contact@example.org" and
                   c["contact_priority"]["outreach_eligible"] for c in response["candidates"])
    assert all("score_type" in c["contact_priority"] for c in response["candidates"])
    # Compact JSON serialization works for the embedding application's MCP adapter.
    json.dumps(response)


def test_conflicting_mailbox_purpose_keeps_both_sources_but_blocks_recommendation():
    # Contradictory published purposes must not silently promote the address.
    a = extract_contacts("<p>Postulez : contact@example.org</p>", "https://example.org/jobs")[0]
    b = extract_contacts("<p>Assistance technique : contact@example.org</p>", "https://example.org/help")[0]
    entries = merge_and_rank([a, b])
    assert len(entries) == 1
    assert entries[0]["contact_priority"]["category"] == "excluded"
    assert entries[0]["exclusion_reason"] == "conflicting_purpose_evidence"
    assert {p["purpose"] for p in entries[0]["purpose_evidence"]} == {"recruitment", "support"}
    assert len(entries[0]["source_urls"]) == 2
    assert len(entries[0]["emails"]) == 2


def test_named_recruiter_with_scoped_general_address_can_be_reviewed():
    html = '''<div class="person"><h3 class="name">Jo Dubois</h3>
    <p class="role">Talent Acquisition Manager</p>
    <a href="mailto:jo.dubois@example.org">jo.dubois@example.org</a></div>'''
    candidate = rank_contact(extract_contacts(html, TEAM)[0])
    assert candidate["purpose"] == "recruitment"
    assert candidate["emails"][0]["purpose"] == "recruitment"
    assert candidate["contact_priority"]["category"] == "named_recruiter"
    assert candidate["contact_priority"]["outreach_eligible"] is True
    assert candidate["contact_priority"]["recommended_action"] == "verify_employer_identity"
