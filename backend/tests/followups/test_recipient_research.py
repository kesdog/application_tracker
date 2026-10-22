"""Tracker adaptation contracts; toolbox owns the generic HTML extraction tests."""
import asyncio

from webtoolbox import merge_and_rank
from webtoolbox.contacts import assess_employer, extract_contacts

from app.recipient_research import PublicRecipientResearch
from app.recipient_research import adapt_candidate, matches_company, usable_url, role_for_email, contact_url


class FakeWeb:
    def __init__(self, pages=None, search=None):
        self.pages = pages or {}
        self.search_result = search or {'completion': 'complete', 'attempts': [],
            'results': [{'url': 'https://example.com/contact', 'title': 'Example', 'snippet': ''}]}
        self.crawled = []
        self.options = []
        self.search_options = []

    async def search_with_fallback(self, *args, **kwargs):
        self.search_options.append(kwargs)
        return self.search_result

    async def search(self, *args, **kwargs):
        return {'results': [], 'outcome': 'empty'}

    async def crawl(self, url, **kwargs):
        self.crawled.append(url)
        self.options.append(kwargs)
        result = self.pages.get(url, {'outcome': 'results', 'candidates': []})
        return {'url': url, **result}


def page(html, url='https://example.com/contact', **extra):
    candidates = [assess_employer(c, 'Example') for c in extract_contacts(html, url)]
    return {'outcome': 'results', 'candidates': merge_and_rank(candidates), **extra}


def discover(web, **context):
    researcher = PublicRecipientResearch.__new__(PublicRecipientResearch)
    researcher.web = web
    return asyncio.run(researcher.discover({'company': 'Example', 'job_title': 'Engineer', **context}))


def test_structured_ranked_evidence_is_preserved_and_generic_mailbox_is_a_fallback():
    web = FakeWeb({'https://example.com/contact': page('<p>Contact: info@employer.test</p><p>Recruitment: jobs@employer.test</p>')})
    result = discover(web)
    assert result['outcome'] == 'COMPLETED'
    recruiter, general = result['candidates']
    assert recruiter['email'] == 'jobs@employer.test'
    assert recruiter['contact_priority']['category'] == 'recruitment_mailbox'
    assert recruiter['field_evidence']['email'][0]['source_url'] == recruiter['source_url']
    assert recruiter['search_provenance'][0]['url'] == recruiter['source_url']
    assert general['contact_priority']['recommended_action'] == 'verify_recruitment_purpose'
    assert general['deliverability'] == 'not_checked' and general['personal_ownership'] == 'unknown'
    assert web.search_options[0]['continue_for_contacts'] is True
    assert web.options[0]['max_tokens'] == 14000
    assert web.options[0]['contacts'] and web.options[0]['structured'] and web.options[0]['mode'] == 'auto'


def test_conflicting_mailbox_purposes_are_merged_before_recommendations():
    first = page('<p>Recruitment: jobs@employer.test</p>', fields={'contact_links': ['https://example.com/support']})
    second = page('<p>Support: jobs@employer.test</p>', 'https://example.com/support')
    result = discover(FakeWeb({'https://example.com/contact': first, 'https://example.com/support': second}))
    assert result['candidates'] == []
    excluded = result['diagnostics']['excluded_candidates'][0]
    assert excluded['exclusion_reason'] == 'conflicting_purpose_evidence'
    assert len(excluded['source_urls']) == 2


def test_provider_failure_without_results_is_retryable_and_not_empty():
    result = discover(FakeWeb(search={'completion': 'unresolved', 'results': [],
        'attempts': [{'outcome': 'rate_limited', 'raw_count': 0, 'usable_count': 0}]}))
    assert result['outcome'] == 'FAILED' and result['error']
    assert 'rate_limited' in ' '.join(result['warnings'])
    assert discover(FakeWeb(search={'completion': 'complete', 'results': [], 'attempts': []}))['outcome'] == 'NO_RESULTS'


def test_blocked_rendering_and_truncation_remain_visible_with_partial_contacts():
    links = ['https://example.com/blocked', 'https://example.com/team']
    web = FakeWeb({'https://example.com/contact': page('<p>jobs@employer.test</p>',
        stale=True, upstream_outcome='timeout', fields={'contact_links': links}, truncation={'omitted_records': 1}),
        links[0]: {'outcome': 'blocked'}, links[1]: {'outcome': 'rendering_needed', 'rendering_signals': ['js_shell']}})
    result = discover(web)
    assert result['outcome'] == 'COMPLETED' and result['candidates'][0]['stale']
    warnings = ' '.join(result['warnings'])
    assert all(word in warnings for word in ('blocked', 'rendering_needed', 'budget', 'cached'))
    assert result['diagnostics']['completion'] == 'partial'
    assert discover(FakeWeb({'https://example.com/contact': {'outcome': 'blocked'}}))['outcome'] == 'FAILED'


def test_saved_vacancy_is_crawled_and_supplied_as_context_without_following_other_hosts():
    vacancy = 'https://example.com/jobs/42'
    web = FakeWeb({vacancy: page('<p>jobs@employer.test</p>', vacancy,
        fields={'contact_links': ['https://unrelated.com/contact', 'https://www.bing.com/aclick']} )})
    result = discover(web, job_url=vacancy)
    assert result['candidates']
    assert web.crawled[0] == vacancy
    assert all(option['vacancy_url'] == vacancy for option in web.options)
    assert not any('unrelated.com' in url or 'bing.com' in url for url in web.crawled)


def test_cancellation_propagates_to_release_tracker_lease():
    class Cancelled(FakeWeb):
        async def crawl(self, *args, **kwargs):
            raise asyncio.CancelledError()
    import pytest
    with pytest.raises(asyncio.CancelledError):
        discover(Cancelled())


def test_policy_and_media_noise_is_not_offered_as_recipient_evidence():
    assert not usable_url('https://careers.example.com/cookie-policy')
    assert not usable_url('https://example.com/en/newsroom/brand-center')
    assert role_for_email('globalprteam@employer.test') is None
    assert role_for_email('marketing@employer.test') is None
    assert matches_company('Edenred Group', {'url':'https://www.edenred.com/contact'})
    assert matches_company('Euro-Information', {'url':'https://www.e-i.com', 'title':'EuroInformation'})


def test_vendor_credits_and_policy_links_do_not_consume_the_crawl_budget():
    web=FakeWeb({'https://example.com/contact': page('<p>jobs@employer.test</p>', fields={'contact_links':[
        'https://www.teamtailor.com/en/', 'https://example.com/cookie-policy', 'https://example.com/team']})})
    assert discover(web)['candidates']
    assert web.crawled == ['https://example.com/contact','https://example.com/team']


def test_broader_provider_failure_keeps_specific_search_evidence():
    class ProviderFailure(Exception):
        pass
    class FailingBroader(FakeWeb):
        async def search(self, *args, **kwargs):
            raise ProviderFailure('No results found')
    result=discover(FailingBroader({'https://example.com/contact':page('<p>jobs@employer.test</p>')}))
    assert result['outcome'] == 'COMPLETED' and result['candidates'][0]['email'] == 'jobs@employer.test'
    assert result['diagnostics']['search_attempts'][-1]['error_type'] == 'ProviderFailure'
    assert result['diagnostics']['completion'] == 'partial'


def test_form_example_addresses_are_never_recipient_options():
    result=discover(FakeWeb({'https://example.com/contact':page(
        '<p>Exemple de format attendu : nom@domaine.fr</p>'
        '<p>Veuillez entrer une adresse email valide. Exemple : nom.prenom@domaine.com</p>'
        '<p>Recruitment: jobs@employer.test</p>')}))
    assert [c['email'] for c in result['candidates']] == ['jobs@employer.test']
    excluded=result['diagnostics']['excluded_candidates']
    assert len(excluded) == 2 and all(c['exclusion_reason'] == 'example_or_placeholder_address' for c in excluded)


def test_deduplicated_contacts_retain_stale_observations_from_later_pages():
    first=page('<p>Recruitment: jobs@employer.test</p>', fields={'contact_links':['https://example.com/careers']})
    second=page('<p>Recruitment: jobs@employer.test</p>', 'https://example.com/careers', stale=True)
    result=discover(FakeWeb({'https://example.com/contact':first,'https://example.com/careers':second}))
    assert len(result['candidates']) == 1
    candidate=result['candidates'][0]
    assert candidate['stale'] and len(candidate['source_urls']) == 2
    assert len(candidate['source_observations']) == 2
    assert candidate['source_observations'][1]['cache_stale'] is True


def test_source_region_conflict_and_stale_sources_are_visible_but_need_verification():
    html='<meta name="geo.region" content="USA"><p>Recruitment: jobs@employer.test</p>'
    result=discover(FakeWeb({'https://example.com/contact':page(html)}),location='France')
    candidate=result['candidates'][0]
    assert candidate['fit']['region']['state'] == 'mismatch'
    assert candidate['requires_review'] and not candidate['contact_priority']['outreach_eligible']
    assert candidate['source_region'] == 'USA'
    unknown=discover(FakeWeb({'https://example.com/contact':page(html)}))['candidates'][0]
    assert unknown['fit']['region']['state'] == 'unknown'


def test_toolbox_purpose_checks_preserve_salesforce_roles_and_hr_leadership():
    html='<div class="person"><h3>Jane Doe</h3><span class="role">Chief People Officer</span></div>'
    candidate=discover(FakeWeb({'https://example.com/contact':page(html)}))['candidates'][0]
    assert candidate['kind'] == 'recruiter_hr'
    assert candidate['contact_priority']['category'] == 'named_recruiter'
    assert role_for_email('salesforce.developer@employer.test') == 'general_contact'


def test_contact_frontier_preserves_job_queries_and_prioritizes_join_pages_over_corporate_people():
    assert contact_url('https://example.com/jobs?job=42&icid=top&utm_campaign=one') == 'https://example.com/jobs?job=42'
    join='https://example.com/careers/join-us'
    links=['https://example.com/about/people/social-responsibility',join+'?icid=nav',join+'?icid=footer']
    web=FakeWeb({'https://example.com/contact':page('<p>Contact</p>',fields={'contact_links':links}),
        join:page('<p>Recruitment: jobs@employer.test</p>',join)})
    result=discover(web)
    assert result['candidates'][0]['email'] == 'jobs@employer.test'
    assert web.crawled[1] == join and web.crawled.count(join) == 1
    assert not usable_url('https://example.com/report.pdf')


def test_investor_relations_addresses_are_retained_only_in_diagnostics():
    result=discover(FakeWeb({'https://example.com/contact':page('<p>investor.relations@employer.test</p>')}))
    assert not result['candidates']
    assert result['diagnostics']['excluded_candidates'][0]['exclusion_reason'] == 'not_recruitment_investor_relations'


def test_research_filters_ads_brokers_wrong_company_and_extracts_text_emails_without_ownership_guess():
    assert not usable_url('https://www.bing.com/aclick?x=1')
    assert not usable_url('https://rocketreach.co/person')
    assert not usable_url('https://user:password@employer.test/contact')
    assert matches_company('Powens',{'url':'https://careers.powens.com/','title':'Careers','snippet':''})
    assert not matches_company('Finaxys',{'url':'https://unrelated.org/','title':'Other firm','snippet':'Recruitment'})
    from webtoolbox.contacts import extract_contacts, assess_employer
    from webtoolbox import merge_and_rank
    html = """<p>Write to recrutement@employer.test</p><p>media@employer.test</p>
    <div class="person"><h3>Justine Michel</h3><p class="role">Chief People Officer</p></div>
    <div class="person"><h3>Damien Mat</h3><p class="role">Lead Software Engineer</p></div>"""
    raw = [assess_employer(c, 'Example') for c in extract_contacts(html, 'https://example.com/contact')]
    candidates = [adapt_candidate(c) for c in merge_and_rank(raw)]
    useful = [c for c in candidates if not c['excluded']]
    assert len(useful) == 3
    by_name = {c['name']: c for c in useful}
    assert by_name['Justine Michel']['email'] is None
    assert by_name[None]['email'] == 'recrutement@employer.test' and by_name[None]['kind'] == 'recruiter_hr'
    assert by_name['Damien Mat']['kind'] == 'technical_lead'
    assert all(c['vacancy_match'] == 'unknown' and c['company_match'] == 'unknown' for c in useful)
    assert all(c['deliverability'] == 'not_checked' for c in useful)
    assert next(c for c in candidates if c['email'] == 'media@employer.test')['excluded']
