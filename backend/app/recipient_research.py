"""Bounded public research. Returns evidence, never chooses or guesses a recipient."""
import re
import unicodedata
from urllib.parse import urlsplit

EMAIL = re.compile(r'[A-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}', re.I)
BROKERS = ('rocketreach.co','contactout.com','getprospect.com','leadiq.com','zeliq.com','lusha.com','apollo.io')
ATS = ('teamtailor.com','greenhouse.io','lever.co','welcometothejungle.com')
UNSUITABLE_PAGE = re.compile(r'cookie|privacy|confidentialit|mentions-legales|legal-notice|newsroom|brand-center|/press(?:/|$)', re.I)
RECIPE = {'fields': {
    'emails': {'selector': "a[href^='mailto:']", 'attribute':'href', 'pattern':r'^mailto:([^?]+)', 'all':True,'max_items':30},
    'contact_links': {'selector': "a[href*='contact'],a[href*='career'],a[href*='recrut'],a[href*='departments/human'],a[href*='departments/engineering'],a[href*='equipe'],a[href*='our-team']", 'attribute':'href','absolute_url':True,'all':True,'max_items':30},
}}


def normalized(value):
    return re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()).strip()


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
    local = email.split('@')[0].lower()
    if re.search(r'media|press|presse|privacy|dpo|support|sales|marketing|globalpr|security|abuse|noreply|no-reply|donotreply',local):
        return None
    return 'recruiter_hr' if re.search(r'recrut|recruit|career|talent|jobs|^hr$|^rh$',local) else 'general_contact'


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
    # Visible form examples are published strings, not contact methods.
    example = bool(email and (re.search(r'\b(?:exemple|example)\s*(?::|de\s+format|d.adresse|address|email)|\bplaceholder\b|\bformat\s+attendu\b',
        EMAIL.sub('', ' '.join(excerpts)), re.I)
        or re.fullmatch(r'(?:nom|prenom|nom[._-]prenom|prenom[._-]nom)@(?:domaine|domain)\.[a-z]+', email, re.I)))
    excluded = bool(candidate.get('exclusion_reason') or priority.get('category') == 'excluded'
        or example
        or (email and role_for_email(email) is None)
        or any(e.get('exclusion_reason') for e in candidate.get('emails', []) if e.get('email') == email))
    return {**candidate, 'exclusion_reason': 'example_address' if example else candidate.get('exclusion_reason'),
        'kind': kind, 'evidence': ' · '.join(dict.fromkeys(excerpts))[:600],
        'company_match': candidate.get('employer_match', {}).get('state', 'unknown'),
        'vacancy_match': candidate.get('vacancy_responsibility', 'unknown'),
        'email_status': candidate.get('publication', 'unknown'), 'stale': stale, 'excluded': excluded}


class PublicRecipientResearch:
    def __init__(self, cache_path):
        from webtoolbox import Settings, WebToolbox
        self.web = WebToolbox(Settings(cache_path=cache_path, concurrent_fetches=5,
            per_host_concurrency=1, background_concurrency=5, request_timeout=15))

    async def close(self):
        await self.web.close(cancel_pending=True)

    async def discover(self, context):
        import asyncio
        import time
        from webtoolbox import merge_and_rank

        company = context['company']
        deadline = time.monotonic() + 110
        warnings, attempts, pages, raw = [], [], [], []
        incomplete = False
        search = await self.web.search_with_fallback(company[:160], role=context['job_title'][:200],
            limit=6, max_attempts=2, deadline_seconds=35, max_tokens=8000)
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
            not bool(re.search(r'contact|career|recrut|team|equipe', urlsplit(h['url']).path, re.I))))
        pending = [h['url'] for h in hits]
        vacancy_url = context.get('job_url')
        if vacancy_url and usable_url(vacancy_url):
            pending.insert(0, vacancy_url)
        seen = set()
        while pending and len(pages) < 6:
            url = pending.pop(0)
            if url in seen or not usable_url(url):
                continue
            if time.monotonic() >= deadline:
                incomplete = True
                warnings.append('Research deadline reached; retry to check remaining pages.')
                break
            seen.add(url)
            try:
                page = await asyncio.wait_for(self.web.crawl(url, recipe=RECIPE, contacts=True,
                    structured=True, mode='auto', employer=company, include_text=True,
                    vacancy_url=vacancy_url, max_tokens=8000), timeout=min(18, deadline-time.monotonic()))
            except Exception as exc:
                page = {'url': url, 'outcome': 'timeout' if isinstance(exc, TimeoutError) else 'upstream_error'}
            outcome = page.get('outcome', 'results')
            pages.append({k: page.get(k) for k in ('url', 'outcome', 'upstream_outcome', 'cached', 'stale', 'truncation', 'rendering_signals')})
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
            if not match:
                if outcome == 'results':
                    warnings.append('Skipped a page that did not substantiate the employer match.')
                continue
            for candidate in page.get('candidates', []):
                raw.append({**candidate, 'stale': bool(page.get('stale')),
                    'search_provenance': [h for h in hits if h['url'] == url]})
            host = urlsplit(page['url']).hostname
            follow = []
            links = list(page.get('fields', {}).get('contact_links', []))
            links += [link['url'] for link in page.get('contact_links', [])]
            for link in dict.fromkeys(links):
                target = urlsplit(link).hostname
                same_site = target and host and (target == host or target.endswith('.'+host) or host.endswith('.'+target))
                # Bare ATS vendor links are website credits, not employer careers sites.
                employer_ats = target and any(target.endswith('.'+a) for a in ATS) and matches_company(company, {'url':link})
                if same_site or employer_ats:
                    if usable_url(link) and link not in seen:
                        follow.append(link)
            follow.sort(key=lambda link: (not bool(re.search(r'contact|team|equipe|human|engineering', urlsplit(link).path, re.I)), len(link)))
            pending = follow[:2] + pending
        if pending:
            incomplete = True
            warnings.append('Six-page research limit reached; additional pages remain unchecked.')
        ranked = merge_and_rank(raw)
        # Merge before excluding so contradictory purpose claims cannot become recommendations.
        all_candidates = []
        for candidate in ranked:
            observations = [c for c in raw if c.get('source_url') in candidate.get('source_urls', [])
                and all(c.get(key) == candidate.get(key) for key in ('name', 'role', 'email'))]
            adapted = adapt_candidate(candidate, stale=any(c.get('stale', False) for c in observations))
            adapted['source_observations'] = [{k: c.get(k) for k in ('source_url', 'fetched_at', 'stale', 'source_last_updated')}
                for c in observations]
            adapted['search_provenance'] = list({h['url']: h for c in observations for h in c.get('search_provenance', [])}.values())
            all_candidates.append(adapted)
        candidates = [c for c in all_candidates if not c['excluded'] and (c.get('name') or c.get('email'))][:30]
        outcome = 'COMPLETED' if candidates else 'FAILED' if incomplete else 'NO_RESULTS'
        return {'candidates': candidates, 'warnings': list(dict.fromkeys(warnings)), 'outcome': outcome,
            'error': 'Research incomplete. Retry or enter a known recipient manually.' if outcome == 'FAILED' else None,
            'diagnostics': {'search_attempts': attempts, 'pages': pages, 'completion': 'partial' if incomplete else 'complete',
                'excluded_candidates': [c for c in all_candidates if c['excluded']]}}
