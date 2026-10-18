"""Deterministic regressions from the 18 Oct v0.6 job discovery audit.

All URLs and pages here are test fixtures; no access-control or live requests.
"""
import json
from pathlib import Path
import httpx
import pytest
import webtoolbox.core as core
from webtoolbox import Settings, WebToolbox
from webtoolbox.job_postings import (job_route, is_specific_job_url, parse_job_page,
                                      is_individual_job_page, match_job)

ISCOD = "https://www.iscod.fr/offres-emploi-en-alternance/alternance-developpeur-full-stack-balma-f-h-32d9dg"
INTM = "https://intm.com/project/ingenieur-systeme-h-f/"
HELLOWORK = "https://www.hellowork.com/fr-fr/emplois/77123456.html"
CDI = "https://jobs.lever.co/theodo/86f6912f-70aa-4b62-8933-da41e85c61e7"
STAGE = "https://jobs.lever.co/theodo/1c3bcaf0-0c5b-4728-943a-c7e79c9af035"
FORM = CDI + "/apply"


def html(title="Développeur Full Stack", company="Example Corp", location="Paris", contract="FULL_TIME", apply=True, reference=""):
    # Use one JobPosting per page; distinguish the employer from a board publisher.
    record = {"@type": "JobPosting", "title": title,
              "hiringOrganization": {"name": company},
              "jobLocation": {"address": {"addressLocality": location}},
              "employmentType": contract}
    if reference:
        record["identifier"] = {"value": reference}
    link = '<a href="/apply/now">Apply now</a>' if apply else ""
    return f'<html><head><script type="application/ld+json">{json.dumps(record)}</script></head><body><main><h1>{title}</h1><p>{company} {location}</p>{link}</main></body></html>'


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # Never resolve internet hostnames during offline tests.
    monkeypatch.setattr(core, "validate_url", lambda url, **kwargs: url)
    return Settings(cache_path=tmp_path / "cache.sqlite3", domain_delay_seconds=0,
                    max_job_discovery_pages=12, max_search_results=15)


def test_realistic_platform_routes_and_category_rejection():
    assert job_route(ISCOD)["kind"] == "specific"
    assert job_route(HELLOWORK)["kind"] == "specific"
    assert job_route(INTM)["kind"] == "inspect"
    assert is_specific_job_url(ISCOD)
    assert not is_specific_job_url(INTM)  # Page evidence is still required.
    assert job_route("https://iscod.fr/offres-emploi-en-alternance/")["kind"] == "non_job"
    assert job_route("https://hellowork.com/fr-fr/alternance/metier_developpeur.html")["kind"] == "non_job"
    assert job_route("https://intm.com/project/")["kind"] == "non_job"
    assert job_route(FORM)["kind"] == "application"


async def test_known_iscod_seed_fetched_and_kept(settings, monkeypatch):
    calls = []
    async def fetch(self, url):
        calls.append(url)
        return html(company="ISCOD", location="Balma", contract="INTERN"), url
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(settings) as web:
        response = await web.discover_job("LIVRACT", "Développeur Full Stack", location="Balma",
                                         contract_type="alternance", pages=1, seed_urls=(ISCOD,), max_tokens=8000)
    assert calls == [ISCOD]
    assert response["matches"][0]["publisher"] == "ISCOD"
    assert response["matches"][0]["company"] == ""  # School != confirmed employer.
    assert "employer_unverified" in response["matches"][0]["match"]["evidence"]


async def test_unknown_project_route_requires_evidence(settings, monkeypatch):
    seen=[]
    async def fetch(self,url):
        seen.append(url)
        return html(title="Ingénieur système"), url
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(settings) as web:
        result=await web.discover_job("Example Corp", "Ingénieur système", seed_urls=(INTM,), pages=1, max_tokens=8000)
    assert seen == [INTM]
    assert len(result["matches"]) == 1
    assert not is_individual_job_page(parse_job_page("<h1>Nos offres</h1>", INTM), INTM)


async def test_category_flood_does_not_stop_second_query(settings, monkeypatch):
    seen=[]
    page=html(title="Développeur C#", company="ACME")
    async def fetch(self,url):
        seen.append(url)
        return page,url
    async def provider(query,limit):
        if "first" in query:
            return [{"url":f"https://acme.com/jobs/search?page={i}","title":"Jobs"} for i in range(7)]
        return [{"url":"https://acme.com/jobs/112223", "title":"Développeur C#"}]
    monkeypatch.setattr(WebToolbox,"_static_fetch",fetch)
    monkeypatch.setattr(core,"ddgs_search",provider)
    profile={"job_queries":["first {company}","second {company}"]}
    async with WebToolbox(settings) as web:
        result=await web.discover_job("ACME", "Développeur C#",pages=1,keyword_profile=profile,max_tokens=8000)
    assert seen==["https://acme.com/jobs/112223"]
    assert result["query_count"]==2 and len(result["matches"])==1
    assert result["route_rejection_count"] == 7
    assert result["query_stop_reason"] == "eligible_route_cap"


def test_contract_conflict_caps_near_match_even_with_same_title():
    page=parse_job_page(html(title="Software engineer IA Backend",company="Theodo",contract="INTERN"),STAGE)
    match=match_job(page,title="Software engineer IA Backend",company="Theodo",contract_type="CDI")
    assert match["score"]<=29 and match["status"]!="likely_match"
    assert "contract_mismatch" in match["hard_conflicts"]
    assert match_job(page,title="Software engineer IA Backend",company="Theodo",contract_type="stage")["status"]=="likely_match"


def test_search_snippet_cannot_certify_company_and_url_city_is_observed():
    missing=parse_job_page(html(title="Developpeur IA",company="",location="Paris",contract="CDI"),CDI)
    missing["company"]=""
    result=match_job(missing,title="Developpeur IA",company="ADVANCED Schema",
                     search_hit={"snippet":"ADVANCED Schema recrute"})
    assert "employer_missing" in result["evidence"] and "employer_schema_match" not in result["evidence"]
    nantes=parse_job_page("<html><main><h1>Développeur Java</h1><a href='/apply'>Postuler</a></main></html>",
                           "https://capgemini.com/jobs/developpeur-java-nantes-91919")
    assert nantes["location"]=="nantes" and nantes["location_evidence"]=="url_slug"
    mismatch=match_job(nantes,title="Développeur Java",location="Paris")
    assert "location_mismatch" in mismatch["hard_conflicts"]


async def test_filter_mode_reaches_underlying_search(settings,monkeypatch):
    async def provider(q,limit):
        return [{"url":"https://acme.com/jobs/101", "title":"Senior Java"},
                {"url":"https://acme.com/jobs/102", "title":"Python alternance"}]
    async def fetch(self,url): return html(title="Python alternance"),url
    monkeypatch.setattr(core,"ddgs_search",provider)
    monkeypatch.setattr(WebToolbox,"_static_fetch",fetch)
    async with WebToolbox(settings) as web:
        result=await web.discover_job("Acme", "Python alternance", pages=2,
                keyword_mode="filter", keyword_profile={"keywords":{"required":["python"]}}, max_tokens=8000)
    assert result["keyword_mode"]=="filter"
    assert result["inspected_page_count"]==1
    assert any(a["keyword_omitted"] for a in result["search_attempts"])


async def test_application_form_is_destination_not_second_posting(settings,monkeypatch):
    async def provider(q,limit): return [{"url":FORM,"title":"Apply"},{"url":CDI,"title":"Software engineer"}]
    async def fetch(self,url): return html(title="Software engineer",company="Theodo"),url
    monkeypatch.setattr(core,"ddgs_search",provider)
    monkeypatch.setattr(WebToolbox,"_static_fetch",fetch)
    async with WebToolbox(settings) as web:
        result=await web.discover_job("Theodo","Software engineer",pages=2,max_tokens=8000)
    assert len(result["matches"]) == 1
    assert result["application_destinations"][0]["url"] == FORM
    assert result["route_rejection_count"] >= 1


async def test_rate_limited_host_defers_sibling_not_observed_429(settings,monkeypatch):
    urls=("https://acme.com/jobs/101","https://acme.com/jobs/102")
    requested=[]
    async def fetch(self,url):
        requested.append(url)
        request=httpx.Request("GET",url)
        raise httpx.HTTPStatusError("rate limited",request=request,response=httpx.Response(429,request=request))
    monkeypatch.setattr(WebToolbox,"_static_fetch",fetch)
    async with WebToolbox(settings) as web:
        # This seed-only cooldown test must never call a live search provider.
        response=await web.discover_job("Acme","Python",seed_urls=urls,pages=2,
                                        keyword_profile={"job_queries": []},max_tokens=8000)
    assert requested==[urls[0]]
    outcomes=[a["outcome"] for a in response["search_attempts"] if a["stage"]=="crawl"]
    assert outcomes == ["rate_limited", "deferred_host_cooldown"]


async def test_requested_effective_cap_and_search_title_preserve_identity(settings,monkeypatch):
    settings.max_job_discovery_pages=1
    queries=[]
    async def provider(query,limit):
        queries.append(query)
        return [{"url":CDI,"title":"Senior Python Engineer","snippet":"Theodo"}]
    async def fetch(self,url): return html(title="Senior Python Engineer", company="Theodo",contract="FULL_TIME"), url
    monkeypatch.setattr(core,"ddgs_search",provider)
    monkeypatch.setattr(WebToolbox,"_static_fetch",fetch)
    async with WebToolbox(settings) as web:
        result=await web.discover_job("Theodo","Senior Python Engineer (CDI)",search_title="Python Engineer",
            contract_type="CDI",pages=12,keyword_profile={"job_queries":["{company} {title}"]},max_tokens=8000)
    assert result["requested_page_cap"]==12 and result["effective_page_cap"]==1
    assert queries == ["Theodo Python Engineer"]
    assert result["title"]=="Senior Python Engineer (CDI)"
    assert result["search_title"]=="Python Engineer"


async def test_known_410_is_url_unavailable_not_global_hiring_decision(settings,monkeypatch):
    async def fetch(self,url):
        req=httpx.Request("GET",url)
        raise httpx.HTTPStatusError("gone",request=req,response=httpx.Response(410,request=req))
    monkeypatch.setattr(WebToolbox,"_static_fetch",fetch)
    async with WebToolbox(settings) as web:
        result=await web.check_job_status(ISCOD,max_tokens=8000)
    assert result["status"]=="CLOSED" and result["reason"]=="posting_unavailable"
    assert result["http_status"]==410


def test_confirmed_domain_can_support_missing_employer_only_with_evidence():
    from webtoolbox import EmployerContext
    page=parse_job_page('<html><main><h1>Ingénieur Python</h1><p>Vos missions et candidature</p><a href="/apply">Postuler</a></main></html>',
                        'https://jobs.acme.fr/jobs/python-engineer-12345')
    ctx=EmployerContext(company='Acme',domain='acme.fr',status='confirmed',evidence_source='user_confirmed')
    without=match_job(page,title='Ingénieur Python',company='Acme',source_url='https://jobs.acme.fr/jobs/python-engineer-12345')
    with_ctx=match_job(page,title='Ingénieur Python',company='Acme',employer_context=ctx,
                       source_url='https://jobs.acme.fr/jobs/python-engineer-12345')
    assert without['employer_identity']=='unverified'
    assert without['status']=='possible_match'
    assert with_ctx['employer_identity']=='confirmed_by_source'
    assert with_ctx['status']=='likely_match'


def test_known_city_conflict_and_reference_mismatch_cannot_be_likely():
    page=parse_job_page(html(title='Ingénieur Python',company='Acme',location='Nantes',reference='ROLE-234'),
                        'https://acme.com/jobs/python-nantes-123')
    outcome=match_job(page,title='Ingénieur Python',company='Acme',location='Paris',reference='ROLE-233')
    assert outcome['hard_conflicts']==['location_mismatch','reference_mismatch']
    assert outcome['score']<=29


async def test_http_redirect_to_specific_job_is_preserved(settings,monkeypatch):
    original='https://jobs.lever.co/theodo/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    moved='https://jobs.lever.co/theodo/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
    async def fetch(self,url):return html(title='Software Engineer',company='Theodo'),moved
    monkeypatch.setattr(WebToolbox,'_static_fetch',fetch)
    async with WebToolbox(settings) as web:
        response=await web.discover_job('Theodo','Software Engineer',seed_urls=(original,),pages=1,max_tokens=8000)
    assert response['matches'][0]['posting_url']==moved
    assert response['matches'][0]['redirected_from']==original
    assert response['matches'][0]['instance_equivalence']=='verified_http_redirect'
    assert response['matches'][0]['posting_identity']['id_type']=='lever_uuid'


def test_declared_canonical_is_not_inferred_instance_equivalence():
    source='https://acme.com/jobs/developer-12345'
    page=parse_job_page(html() .replace('</head>', '<link rel="canonical" href="https://jobs.lever.co/acme/1234" /></head>'),source)
    assert page['declared_canonical_url']=='https://jobs.lever.co/acme/1234'
    # A publisher-declared canonical is evidence, not a tested HTTP redirect.
    assert 'declared_canonical_url' in page


async def test_blocked_page_cached_across_query_profiles(settings, monkeypatch):
    url='https://jobs.lever.co/theodo/86f6912f-70aa-4b62-8933-da41e85c61e7'
    fetched=[]
    async def fetch(self, requested):
        fetched.append(requested)
        request=httpx.Request('GET', requested)
        raise httpx.HTTPStatusError('rate limited', request=request,
                                    response=httpx.Response(429, request=request))
    monkeypatch.setattr(WebToolbox,'_static_fetch',fetch)
    async with WebToolbox(settings) as web:
        first=await web.discover_job('Theodo','Software Engineer',seed_urls=(url,),pages=1,
                                     keyword_profile={'keywords':{'preferred':{'python':5}}},max_tokens=8000)
        second=await web.discover_job('Theodo','Software Engineer',seed_urls=(url,),pages=1,
                                      keyword_profile={'keywords':{'preferred':{'java':5}}},max_tokens=8000)
    assert fetched == [url]
    assert first['search_attempts'][0]['outcome']=='rate_limited'
    assert first['search_attempts'][0]['cached_failure'] is False
    assert second['search_attempts'][0]['outcome']=='rate_limited'
    assert second['search_attempts'][0]['cached_failure'] is True


async def test_successful_forced_fetch_removes_old_failure(settings, monkeypatch):
    # An operator-initiated refresh can recover a previously blocked page.
    url = CDI
    calls=0
    async def fetch(self,requested):
        nonlocal calls
        calls+=1
        if calls==1:
            request=httpx.Request('GET',requested)
            raise httpx.HTTPStatusError('rate limited',request=request,
                                        response=httpx.Response(429,request=request))
        return html(title='Software Engineer',company='Theodo'),requested
    monkeypatch.setattr(WebToolbox,'_static_fetch',fetch)
    async with WebToolbox(settings) as web:
        failed=await web.discover_job('Theodo','Software Engineer',seed_urls=(url,),pages=1,max_tokens=8000)
        recovered=await web.check_job_status(url,refresh=True,max_tokens=8000)
        future=await web.discover_job('Theodo','Software Engineer',seed_urls=(url,),pages=1,max_tokens=8000)
    assert failed['search_attempts'][0]['outcome']=='rate_limited'
    assert recovered['status']=='LIVE'
    assert future['matches'] and future['matches'][0]['cached'] is True
    assert calls==2
