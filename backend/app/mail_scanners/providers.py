from dataclasses import dataclass
from email.utils import parseaddr
import re
import unicodedata
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from app.confirmation_links import _decoded, extract_confirmation_link
from app.mail_scanners.languages import LANGUAGES, applied_date, has_update_signals, lifecycle, normalized
from app.mail_scanners.models import ConfirmationDetails, ScanResult


@dataclass
class MailContent:
    html: str
    text: str
    soup: BeautifulSoup
    headers: dict
    posting: dict

    @classmethod
    def parse(cls, content, headers=None, text=None):
        soup = BeautifulSoup(_decoded(content), 'html.parser')
        for quoted in soup.select('blockquote, .gmail_quote, .gmail_extra, .yahoo_quoted, script, style'):
            quoted.decompose()
        html = str(soup)
        raw = soup.get_text(' ') if text is None else text
        value = re.sub(r'\s+', ' ', ''.join(c for c in raw if unicodedata.category(c) != 'Cf')).strip()
        return cls(html, value, soup, {key.lower(): value for key, value in (headers or {}).items()},
                   extract_confirmation_link(html or 'Unrecognized email').model_dump())

    def sender_is(self, *domains):
        host = parseaddr(self.headers.get('from', ''))[1].rpartition('@')[2].lower().rstrip('.')
        return any(host == domain or host.endswith('.' + domain) for domain in domains)

    def links_to(self, domain):
        return any((urlsplit(str(a['href'])).hostname or '').lower().rstrip('.') in (domain, 'www.' + domain)
                   for a in self.soup.find_all('a', href=True))


class MailScanner:
    name = 'generic'
    source = None

    def matches(self, content):
        return True

    def result(self, content, *, title=None, company=None, intermediary=None, kind='UNRECOGNIZED', matched=None,
               language=None, reason='No unambiguous role/employer confirmation pattern found; review the message body', posting=None):
        decision, decision_language = lifecycle(content.text)
        if kind == 'APPLICATION_CONFIRMATION' and has_update_signals(content.text):
            kind = 'APPLICATION_UPDATE'
        if title and len(title) > 300:
            title = None
        if company and (len(company) > 300 or company.casefold() in {"notre entreprise", "our company", "l'entreprise", "l’entreprise"}):
            company = None
        if company and company.casefold() in {'iscod', "l'iscod", 'l’iscod', 'iscod, la formation en alternance'}:
            company, intermediary = None, 'ISCOD'
            reason = 'ISCOD is the intermediary; this confirmation does not disclose the partner employer'
        posting = posting or content.posting
        if not posting.get('source') and kind != 'UNRECOGNIZED' and self.source:
            posting = {**posting, 'source': self.source}
        details = ConfirmationDetails(title, company, intermediary, kind, matched, applied_date(content.text), posting, reason)
        return ScanResult(details, decision, self.name, language or decision_language)


class GenericScanner(MailScanner):
    """Explicit evidence only; never infer an employer from the sender brand."""
    name = 'generic'

    def scan(self, content):
        forwarding = re.search(r"votre CV a été envoyé à l[’']entreprise (.+?) qui recherche", content.text, re.I)
        if forwarding and re.search(r'\bISCOD\b', content.text, re.I):
            company = re.sub(r'\s*-\s*IT$', '', forwarding[1]).strip()
            title = None
            if content.posting.get('job_url'):
                labels = {a.get_text(' ', strip=True) for a in content.soup.find_all('a', href=True)
                          if str(a['href']).rstrip('/') == content.posting['job_url'].rstrip('/')}
                labels = {label for label in labels if 5 <= len(label) <= 300 and not re.match(
                    r'^(?:voir|consulter|ouvrir|en savoir|clique[rz]|view|open|read|learn|apply|postuler|candidater)\b', normalized(label))}
                if len(labels) == 1:
                    title = labels.pop()
            return self.result(content, title=title, company=company, intermediary='ISCOD', kind='CV_FORWARDED',
                               matched=forwarding[0], language='fr', reason='ISCOD forwarded the CV to the named partner employer; no offer or interview is implied')
        for pack in LANGUAGES:
            for pattern in pack.confirmations:
                found = re.search(pattern, content.text, re.I)
                if found:
                    return self.result(content, title=found[1].strip(), company=found[2].strip(),
                                       kind='APPLICATION_CONFIRMATION', matched=found[0], language=pack.code,
                                       reason='Role and employer extracted from the confirmation body, not the sender')
        return self.result(content)


class IndeedScanner(MailScanner):
    name = 'indeed'
    source = 'INDEED'

    def matches(self, content):
        return content.sender_is('indeed.com', 'indeed.fr', 'indeed.co.uk', 'indeed.de') or content.posting.get('source') == 'INDEED' or any(
            re.search(pack.sent_to, content.text, re.I) for pack in LANGUAGES)

    def scan(self, content):
        for pack in LANGUAGES:
            advertiser = re.search(pack.sent_to, content.text, re.I)
            if not advertiser:
                continue
            company = advertiser[1].strip()
            role = re.search(pack.sent_prefix + r' (.+?)\s+' + re.escape(company) +
                             r'\s+-\s+.+?\s+(?:' + pack.sent_to + ')', content.text, re.I)
            if role:
                return self.result(content, title=role[1].strip(), company=company, kind='APPLICATION_CONFIRMATION',
                                   matched=role[0], language=pack.code, reason='Indeed confirmation names the role and advertiser')
        return self.result(content)


class LinkedInScanner(MailScanner):
    name = 'linkedin'
    source = 'LINKEDIN'

    def matches(self, content):
        return content.sender_is('linkedin.com') or content.posting.get('source') == 'LINKEDIN' or any(
            re.search(pack.linkedin_prefix, content.text, re.I) for pack in LANGUAGES)

    def scan(self, content):
        for pack in LANGUAGES:
            # Preview text can repeat the heading; use the final application card.
            cards = re.split(pack.linkedin_prefix, content.text, flags=re.I)
            if len(cards) < 2:
                continue
            found = re.search(r'^(.+?)\s+(.+?)\s+\1\s*·', cards[-1], re.I)
            if not found:
                continue
            company, title = found[1].strip(), found[2].strip()
            job_id = re.search(r'/jobs/view/(\d+)', content.posting.get('job_url') or '')
            if job_id:
                labels = [a.get_text(' ', strip=True) for a in content.soup.find_all('a', href=True)
                          if re.search(r'/jobs/view/(?:[^/]*-)?' + job_id[1] + r'(?:/|[?#]|$)', str(a['href']))]
                labels = [label for label in labels if label and '·' not in label]
                if labels:
                    title = min(labels, key=len)
                    heading = next((h.get_text(' ', strip=True) for h in content.soup.find_all(('h1', 'h2'))
                                    if re.match(pack.linkedin_prefix, h.get_text(' ', strip=True), re.I)), None)
                    if heading:
                        company = re.sub('^' + pack.linkedin_prefix, '', heading, flags=re.I).strip()
            return self.result(content, title=title, company=company, kind='APPLICATION_CONFIRMATION',
                               matched=found[0], language=pack.code, reason='LinkedIn application card names the employer and role')
        return self.result(content)


class FreeWorkScanner(MailScanner):
    name = 'freework'
    source = 'FREEWORK'

    def matches(self, content):
        return content.sender_is('free-work.com') or content.links_to('free-work.com')

    def scan(self, content):
        for pack in LANGUAGES:
            for pattern in pack.freework:
                found = re.search(pattern, content.text, re.I)
                if not found:
                    continue
                posting = content.posting
                links = {str(a['href']) for a in content.soup.find_all('a', href=True)
                         if (urlsplit(str(a['href'])).hostname or '').lower() in ('free-work.com', 'www.free-work.com')
                         and re.search(r'/(?:job-mission|offre)/[^/]+', urlsplit(str(a['href'])).path)}
                if len(links) == 1:
                    url = links.pop()
                    posting = {'job_url': url, 'source': 'FREEWORK', 'confirmation_url': url,
                               'reason': 'Free-Work confirmation links a specific vacancy'}
                return self.result(content, title=found[1].strip(), company=found[2].strip(),
                                   kind='APPLICATION_CONFIRMATION', matched=found[0], language=pack.code,
                                   posting=posting, reason='Free-Work explicitly confirms the submitted application')
        return self.result(content)
