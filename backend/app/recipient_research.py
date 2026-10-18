"""Bounded public research. Returns evidence, never chooses or guesses a recipient."""
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

BROKERS = ('rocketreach.co','contactout.com','getprospect.com','leadiq.com','zeliq.com','lusha.com','apollo.io')
ATS = ('teamtailor.com','greenhouse.io','lever.co','welcometothejungle.com')
UNSUITABLE_PAGE = re.compile(r'cookie|privacy|confidentialit|mentions-legales|legal-notice|newsroom|brand-center|data-protection|/press(?:/|$)|/login(?:/|$)|/connect(?:/|$)|\.(?:pdf|docx?|xlsx?)$', re.I)
RECIPE = {'fields': {
    'emails': {'selector': "a[href^='mailto:']", 'attribute':'href', 'pattern':r'^mailto:([^?]+)', 'all':True,'max_items':30},
    'contact_links': {'selector': "a[href*='contact'],a[href*='career'],a[href*='recrut'],a[href*='departments/human'],a[href*='departments/engineering'],a[href*='equipe'],a[href*='our-team']", 'attribute':'href','absolute_url':True,'all':True,'max_items':30},
}}


def normalized(value):
    return re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()).strip()


def contact_url(value):
    """Remove navigation tracking, retaining functional vacancy/query parameters."""
    parsed = urlsplit(value)
    query = [(k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('icid','trk','fbclid','gclid')]
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode(query),''))


def page_priority(url, label=''):
    from webtoolbox.frontier import contact_page_priority
    priority = contact_page_priority(url,label)
    if re.search(r'recruit|recrut|postul|join|rejoindre|candidatur', urlsplit(url).path+' '+label, re.I):
        priority += 50
    if re.search(r'contact',urlsplit(url).path,re.I):
        priority += 30
    return priority


def usable_url(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        return bool(host and parsed.scheme in ('http','https') and not parsed.username and not parsed.password
            and not any(host == b or host.endswith('.'+b) for b in BROKERS)
            and not UNSUITABLE_PAGE.search(parsed.path)
            and not (host.endswith('bing.com') or host.endswith('google.com') or host.endswith('yandex.ru'))
            and not re.search(r'/(?:aclick|aclk|click|clck)(?:/|$)',parsed.path))
    except ValueError:
        return False


def matches_company(company, hit):
    brand = normalized(company)
    brand = re.sub(r'\s+(?:group|groupe|inc|ltd|sas|sa)$', '', brand)
    host = (urlsplit(hit['url']).hostname or '').lower()
    compact = brand.replace(' ','')
    if len(compact) >= 4 and compact in host.replace('-','').replace('.',''):
        return 'domain_name'
    text = normalized(hit.get('title','') + ' ' + hit.get('snippet',''))
    if brand and (re.search(r'\b'+re.escape(brand)+r'\b', text)
                  or (' ' in brand and re.search(r'\b'+re.escape(compact)+r'\b', text))):
        return 'search_title_or_snippet'
    return None


def role_for_email(email):
    from webtoolbox.contacts import purpose_for
    purpose, excluded = purpose_for(email)
    if excluded or re.search(r'noreply|no-reply|donotreply|security|abuse', email.split('@')[0], re.I):
        return None
    return 'recruiter_hr' if purpose == 'recruitment' else 'general_contact'


def employer_excerpt(company, text):
    """Keep a bounded company mention even when it occurs after the summary budget."""
    brand = re.sub(r'\s+(?:group|groupe|inc|ltd|sas|sa)$', '', normalized(company))
    source = normalized(text)
    for name in (brand, brand.replace(' ', '')):
        match = re.search(r'\b'+re.escape(name)+r'\b', source) if name else None
        if match:
            start = max(0, match.start()-120)
            return source[start:start+600]
    return ''



def adapt_candidate(candidate, *, stale=False):
    """Keep toolbox evidence intact while supplying the tracker's presentation fields."""
    email = candidate.get('email')
    priority = candidate.get('contact_priority', {})
    kind = 'general_contact'
    if priority.get('category') in ('named_recruiter', 'recruitment_mailbox') or candidate.get('purpose') == 'recruitment':
        kind = 'recruiter_hr'
    elif re.search(r'engineer|engineering|CTO|tech|développe', candidate.get('role') or '', re.I):
        kind = 'technical_lead'
    evidence = candidate.get('field_evidence', {})
    excerpts = [e.get('excerpt', '') for e in evidence.get('email', [])]
    excerpts += [evidence[key]['excerpt'] for key in ('name', 'role') if evidence.get(key)]
    stale = bool(stale or candidate.get('cache_stale'))
    fit = candidate.get('fit', {})
    mismatch = any(fit.get(dimension, {}).get('state') == 'mismatch' for dimension in ('region', 'sector'))
    excluded = bool(candidate.get('exclusion_reason') or priority.get('category') == 'excluded'
        or (email and role_for_email(email) is None)
        or any(e.get('exclusion_reason') for e in candidate.get('emails', []) if e.get('email') == email))
    investor = bool(email and re.search(r'investor|actionnaire|shareholder',email.split('@')[0],re.I))
    return {**candidate, 'excluded': excluded or investor,
        'exclusion_reason': 'not_recruitment_investor_relations' if investor else candidate.get('exclusion_reason'),
        'requires_review': bool(stale or mismatch),
        'kind': kind, 'evidence': ' · '.join(dict.fromkeys(excerpts))[:600],
        'company_match': candidate.get('employer_match', {}).get('state', 'unknown'),
        'vacancy_match': candidate.get('vacancy_responsibility', 'unknown'),
        'email_status': candidate.get('publication', 'unknown'), 'stale': stale}


class PublicRecipientResearch:
    def __init__(self, cache_path, report_store=None):
        from webtoolbox import Settings, WebToolbox
        from app.recipient_reports import SearchOnlyCache
        self.report_store = report_store
        self.web = WebToolbox(Settings(cache_path=cache_path, concurrent_fetches=5,
            per_host_concurrency=1, background_concurrency=5, request_timeout=15))
        self.web.cache = SearchOnlyCache(self.web.cache)

    async def close(self):
        await self.web.close(cancel_pending=True)

    async def discover(self, context):
        import asyncio
        import time
        from webtoolbox import merge_and_rank
        from webtoolbox.contacts import assess_employer
        from webtoolbox.frontier import prioritize_contact_links

        company = context['company']
        from datetime import datetime
        store = getattr(self, 'report_store', None)
        application_id = context.get('application_id')
        page_limit = max(1, min(100, int(context.get('page_limit', 6))))
        refresh_after = datetime.fromisoformat(context['refresh_after']) if context.get('refresh_after') else None
        source_context = {k: context.get(k) for k in ('company', 'job_title', 'job_url', 'location')}
        fetched_count = reused_count = 0
        deferred = []
        deadline = time.monotonic() + 110
        warnings, attempts, pages, raw = [], [], [], []
        incomplete = False
        search = await self.web.search_with_fallback(company[:160], role=context['job_title'][:200],
            limit=10, max_attempts=2, deadline_seconds=35, max_tokens=14000, continue_for_contacts=True)
        attempts.extend(search.get('attempts', []))
        incomplete = search.get('completion') != 'complete'
        hits = [h for h in search.get('results', []) if usable_url(h['url']) and matches_company(company, h)]
        if search.get('completion') != 'unresolved':
            # Vacancy mirrors often lack contacts. Reserve one broader employer/contact search.
            try:
                extra = await asyncio.wait_for(self.web.search(f'{company} official careers contact'[:300],
                    limit=6, max_tokens=8000), timeout=20)
                attempts.append({k: extra.get(k) for k in ('provider', 'outcome', 'raw_count', 'usable_count', 'filtered', 'stale')})
                incomplete |= extra.get('outcome') not in ('results', 'empty') or bool(extra.get('stale'))
                hits += [h for h in extra.get('results', []) if usable_url(h['url']) and matches_company(company, h)]
            except Exception as exc:
                incomplete = True
                attempts.append({'provider': 'ddgs', 'outcome': 'timeout' if isinstance(exc, TimeoutError) else 'upstream_error',
                    'error_type': type(exc).__name__, 'raw_count': 0, 'usable_count': 0})
                warnings.append('Broader employer search failed; retry is available.')
        for attempt in attempts:
            if attempt.get('outcome') not in ('results', 'empty'):
                warnings.append(f"Search provider: {attempt.get('outcome', 'unresolved')}. Results may be incomplete.")
            if attempt.get('stale'):
                warnings.append('Search used older cached results after a provider failure.')
        hits = list({h['url']: h for h in hits}.values())
        # Company-hosted contact and careers pages take precedence over vacancy mirrors.
        hits.sort(key=lambda h: (matches_company(company, h) != 'domain_name',
            -page_priority(h['url'], h.get('title', '')+' '+h.get('snippet', ''))))
        priorities = {contact_url(h['url']): page_priority(h['url'],h.get('title','')+' '+h.get('snippet','')) for h in hits}
        pending = list(priorities)
        if store and application_id:
            pending += await asyncio.to_thread(store.seeds, application_id)
        vacancy_url = context.get('job_url')
        if vacancy_url and usable_url(vacancy_url):
            vacancy_url = contact_url(vacancy_url)
            priorities[vacancy_url] = 1000
            pending.insert(0, vacancy_url)
        seen = set()
        while pending and len(seen) < 500:
            pending = sorted(set(pending)-seen,key=lambda link: (-priorities.get(link,0),link))
            if not pending:
                break
            url = pending.pop(0)
            if url in seen or not usable_url(url):
                continue
            if time.monotonic() >= deadline:
                incomplete = True
                warnings.append('Research deadline reached; retry to check remaining pages.')
                break
            seen.add(url)
            async def fetch():
                try:
                    result = await asyncio.wait_for(self.web.crawl(url, recipe=RECIPE, contacts=True,
                        structured=True, mode='auto', employer=company, include_text=True, refresh=True,
                        vacancy_url=vacancy_url, max_tokens=14000), timeout=min(18, deadline-time.monotonic()))
                    return {**result, 'research_vacancy_url': vacancy_url,
                        'employer_excerpt': employer_excerpt(company, result.get('text', ''))}
                except Exception as exc:
                    return {'url': url, 'outcome': 'timeout' if isinstance(exc, TimeoutError) else 'upstream_error'}
            if store and application_id:
                try:
                    page, fetched = await asyncio.wait_for(store.page(application_id, url, source_context, fetch,
                        allow_fetch=fetched_count < page_limit, refresh_after=refresh_after),
                        timeout=max(.01, deadline-time.monotonic()))
                except TimeoutError:
                    incomplete = True
                    warnings.append('Research deadline reached; saved reports are retained for retry.')
                    break
            elif fetched_count < page_limit:
                page, fetched = await fetch(), True
            else:
                page, fetched = None, False
            if page is None:
                deferred.append(url)
                continue
            fetched_count += int(fetched)
            reused_count += int(not fetched)
            # Derived summaries are sufficient for employer/context checks; no full page is stored.
            page = {**page, 'text': page.get('text', page.get('summary', ''))+' '+page.get('employer_excerpt', '')}
            outcome = page.get('outcome', 'results')
            seen.add(contact_url(page['url']))
            pages.append({**{k: page.get(k) for k in ('url', 'outcome', 'upstream_outcome', 'cached', 'stale', 'truncation', 'rendering_signals')}, 'reused': not fetched})
            if outcome != 'results' or page.get('upstream_outcome'):
                incomplete = True
                warnings.append(f"{urlsplit(url).hostname}: {outcome}. No access restrictions were bypassed.")
            truncation = page.get('truncation', {})
            if truncation.get('omitted_records') or truncation.get('omitted_fields'):
                incomplete = True
                warnings.append(f"{urlsplit(url).hostname}: some whole records or fields exceeded the output budget.")
            if page.get('stale'):
                warnings.append(f"{urlsplit(url).hostname}: older cached evidence; recheck the source.")
            # A snippet alone does not establish which employer the fetched page concerns.
            match = matches_company(company, {'url': page['url'], 'title': page.get('title', ''), 'snippet': page.get('text', '')})
            if not match or not usable_url(page['url']):
                if outcome == 'results':
                    warnings.append('Skipped a page that did not substantiate the employer match.')
                continue
            for candidate in page.get('candidates', []):
                if not fetched and page.get('vacancy_url') != vacancy_url:
                    candidate = {**candidate, 'vacancy_responsibility': 'unknown', 'vacancy_evidence': []}
                assessed = assess_employer(candidate, company, target_region=context.get('location'),
                    source_context={'description': ' '.join((candidate.get('role') or '', page.get('title') or '')),
                        'region': candidate.get('source_region') or '', 'sector': candidate.get('source_sector') or ''})
                raw.append({**assessed, 'cache_stale': bool(page.get('stale')),
                    'search_provenance': [h for h in hits if contact_url(h['url']) == url]})
            host = urlsplit(page['url']).hostname
            follow = []
            links = list(page.get('fields', {}).get('contact_links', []))
            links += [link if isinstance(link, str) else link['url'] for link in page.get('contact_links', [])]
            for link in dict.fromkeys(contact_url(link) for link in links):
                target = urlsplit(link).hostname
                same_site = target and host and (target == host or target.endswith('.'+host) or host.endswith('.'+target))
                # Bare ATS vendor links are website credits, not employer careers sites.
                employer_ats = target and any(target.endswith('.'+a) for a in ATS) and matches_company(company, {'url':link})
                if same_site or employer_ats:
                    if usable_url(link) and link not in seen:
                        follow.append(link)
            # Library normalizes tracking and collapses locale variants before the page budget.
            follow = [entry['url'] for entry in prioritize_contact_links(
                [{'url': link} for link in follow], page['url'])]
            for link in follow:
                priorities[link] = max(priorities.get(link,0),page_priority(link))
            pending += follow
        if deferred or set(pending)-seen:
            incomplete = True
            warnings.append(f'{page_limit}-page new-fetch limit or research deadline reached; additional pages remain unchecked. Saved reports will be reused on retry.')
        ranked = merge_and_rank(raw)
        # Merge before excluding so contradictory purpose claims cannot become recommendations.
        all_candidates = []
        for candidate in ranked:
            observations = [c for c in raw if c.get('source_url') in candidate.get('source_urls', [])
                and all(c.get(key) == candidate.get(key) for key in ('name', 'role', 'email'))]
            adapted = adapt_candidate(candidate)
            adapted['search_provenance'] = list({h['url']: h for c in observations for h in c.get('search_provenance', [])}.values())
            all_candidates.append(adapted)
        candidates = [c for c in all_candidates if not c['excluded'] and (c.get('name') or c.get('email'))][:30]
        outcome = 'COMPLETED' if candidates else 'FAILED' if incomplete else 'NO_RESULTS'
        return {'candidates': candidates, 'warnings': list(dict.fromkeys(warnings)), 'outcome': outcome,
            'error': 'Research incomplete. Retry or enter a known recipient manually.' if outcome == 'FAILED' else None,
            'diagnostics': {'search_attempts': attempts, 'pages': pages, 'completion': 'partial' if incomplete else 'complete',
                'page_limit': page_limit, 'fetched_pages': fetched_count, 'reused_pages': reused_count,
                'excluded_candidates': [c for c in all_candidates if c['excluded']]}}
