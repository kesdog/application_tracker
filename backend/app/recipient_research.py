"""Bounded public research. Returns evidence, never chooses or guesses a recipient."""
import re
import unicodedata
from urllib.parse import urlsplit

EMAIL = re.compile(r'[A-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}', re.I)
BROKERS = ('rocketreach.co','contactout.com','getprospect.com','leadiq.com','zeliq.com','lusha.com','apollo.io')
ATS = ('teamtailor.com','greenhouse.io','lever.co','welcometothejungle.com')
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
            and not (host.endswith('bing.com') or host.endswith('google.com') or host.endswith('yandex.ru'))
            and not re.search(r'/(?:aclick|aclk|click|clck)(?:/|$)',parsed.path))
    except ValueError:
        return False


def matches_company(company, hit):
    brand = normalized(company)
    host = (urlsplit(hit['url']).hostname or '').lower()
    compact = brand.replace(' ','')
    if len(compact) >= 4 and compact in host.replace('-','').replace('.',''):
        return 'domain_name'
    text = normalized(hit.get('title','') + ' ' + hit.get('snippet',''))
    if brand and brand in text:
        return 'search_title_or_snippet'
    return None


def role_for_email(email):
    local = email.split('@')[0].lower()
    if re.search(r'media|press|presse|privacy|dpo|support|sales|security|abuse|noreply|no-reply|donotreply',local):
        return None
    return 'recruiter_hr' if re.search(r'recrut|recruit|career|talent|jobs|^hr$|^rh$',local) else 'general_contact'


def extract_candidates(page, company, company_match):
    text = page.get('text','')
    emails = list(page.get('fields',{}).get('emails',[])) + EMAIL.findall(text)
    result=[]
    for email in dict.fromkeys(e.strip().lower() for e in emails):
        if not EMAIL.fullmatch(email):
            continue
        kind = role_for_email(email)
        if not kind:
            continue
        # A published address is not proof of deliverability or vacancy ownership.
        position = text.lower().find(email)
        excerpt = text[max(0,position-80):position+len(email)+100] if position >= 0 else f'Published mailto link: {email}'
        result.append({'name':None,'email':email,'kind':kind,'role':None,'source_url':page['url'],
            'evidence':excerpt[:300],'company_match':company_match,'vacancy_match':'unconfirmed',
            'email_status':'published','stale':page.get('stale',False)})
    people = re.compile(r'([A-ZÀ-Ý][\wÀ-ÿ-]+(?:[ \t]+[A-ZÀ-Ý][\wÀ-ÿ-]+){1,3})[ \t]*,[ \t]*(Chief People Officer|Lead Software Engineer|Head of Engineering|CTO|Talent Acquisition Manager|HR Director)',re.U)
    for name,role in people.findall(text):
        result.append({'name':name,'email':None,'kind':'technical_lead' if re.search('Engineer|CTO',role) else 'recruiter_hr',
            'role':role,'source_url':page['url'],'evidence':f'{name}, {role}','company_match':company_match,
            'vacancy_match':'unconfirmed','email_status':'not_found','stale':page.get('stale',False)})
    return result


class PublicRecipientResearch:
    def __init__(self, cache_path):
        from webtoolbox import Settings, WebToolbox
        self.web = WebToolbox(Settings(cache_path=cache_path,concurrent_fetches=5,request_timeout=15))

    async def close(self):
        await self.web.close()

    async def discover(self, context):
        company = context['company']
        warnings=[]
        hits=[]
        for query in (f'{company} {context["job_title"]} recruitment contact',f'{company} official careers contact'):
            try:
                search = await self.web.search(query[:300],limit=6,max_tokens=2500)
                hits = [h for h in search.get('results',[]) if usable_url(h['url']) and matches_company(company,h)]
                if hits:
                    break
                warnings.append('Search returned no relevant employer pages.')
            except Exception:
                warnings.append('Search provider unavailable or returned no results.')
        if not hits:
            return {'candidates':[],'warnings':warnings,'outcome':'NO_RESULTS'}
        pending = [(h['url'],matches_company(company,h)) for h in hits]
        seen=set()
        candidates=[]
        # Limit each job to six pages, preserving room for discovered HR/team links.
        pages=0
        while pending and pages < 6:
            url,match=pending.pop(0)
            if url in seen or not usable_url(url):
                continue
            seen.add(url)
            pages+=1
            try:
                page=await self.web.crawl(url,recipe=RECIPE,include_text=True,query='recrutement recruitment human resources engineering contact email talent',max_tokens=4500)
            except Exception:
                warnings.append(f'Could not read {urlsplit(url).hostname}; skipped without bypassing access controls.')
                continue
            # Do not promote a company mentioned only in a search snippet if the page doesn't substantiate it.
            if not matches_company(company,{'url':page['url'],'title':page.get('title',''),'snippet':page.get('text','')}):
                warnings.append('Skipped a page that did not substantiate the employer match.')
                continue
            candidates.extend(extract_candidates(page,company,match))
            host=urlsplit(page['url']).hostname
            follow=[]
            for link in page.get('fields',{}).get('contact_links',[]):
                target=urlsplit(link).hostname
                if target == host or (target and host and (target.endswith('.'+host) or host.endswith('.'+target))) or (target and any(target.endswith('.'+a) or target == a for a in ATS)):
                    if usable_url(link) and link not in seen:
                        follow.append((link,match))
            # Prioritize department/contact pages over unrelated search hits.
            pending=follow[:3]+pending
        unique={}
        for c in candidates:
            unique.setdefault((c['email'],c['name'],c['source_url']),c)
        ordered=sorted(unique.values(),key=lambda c: ({'recruiter_hr':0,'technical_lead':1,'general_contact':2}[c['kind']],not bool(c['email'])))
        return {'candidates':ordered[:30],'warnings':list(dict.fromkeys(warnings)),'outcome':'COMPLETED' if ordered else 'NO_RESULTS'}
