"""Tracker-owned derived evidence. Never persist HTML or a complete page body."""
import asyncio
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from app.applications import ApplicationNotFound, get_application
from app.followup_templates import RevisionConflict, current_settings
from app.models import GeneralSettings, RecipientCandidate, RecipientPageReport, RecipientPageUse, utc_now


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    refresh_pages: bool = False


class ResearchSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recipient_page_limit: int = Field(ge=1, le=100)
    expected_revision: int = Field(ge=1)


class ReportQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    application_id: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


def research_settings(session):
    values = current_settings(session)
    return {'recipient_page_limit': values['recipient_page_limit'], 'revision': values['revision'],
        'min_page_limit': 1, 'max_page_limit': 100, 'saved_pages_reused': True}


def update_settings(session, data):
    session.execute(text('BEGIN IMMEDIATE'))
    current_settings(session)
    record = session.get(GeneralSettings, 1)
    if record.revision != data.expected_revision:
        raise RevisionConflict('Settings changed in another session. Reload before saving.')
    if record.values.get('recipient_page_limit', 6) != data.recipient_page_limit:
        record.values = {**record.values, 'recipient_page_limit': data.recipient_page_limit}
        record.revision += 1
    session.commit()
    return research_settings(session)


def page_key(url):
    from app.recipient_research import contact_url
    from urllib.parse import urlsplit, urlunsplit
    parsed = urlsplit(contact_url(url))
    host = parsed.netloc.lower()
    if parsed.scheme == 'https' and host.endswith(':443') or parsed.scheme == 'http' and host.endswith(':80'):
        host = host.rsplit(':', 1)[0]
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or '/', parsed.query, ''))


def clean(value, depth=0):
    """Bound nested evidence and discard raw content even from future toolbox fields."""
    if depth > 10:
        return None
    if isinstance(value, str):
        return value[:2048]
    if isinstance(value, list):
        return [clean(v, depth+1) for v in value[:100]]
    if isinstance(value, dict):
        return {k: clean(v, depth+1) for k, v in list(value.items())[:100]
            if k.lower() not in ('html', 'raw_html', 'body', 'text', 'page_content', 'content')}
    return value if value is None or isinstance(value, (int, float, bool)) else str(value)[:200]


CANDIDATE_FIELDS = ('name', 'email', 'emails', 'role', 'purpose', 'source_url', 'source_urls',
    'field_evidence', 'profile_urls', 'fetched_at', 'source_last_updated', 'source_dates',
    'source_region', 'source_sector', 'publication', 'deliverability', 'personal_ownership',
    'vacancy_responsibility', 'vacancy_reference', 'exclusion_reason', 'contact_priority',
    'employer_match', 'fit', 'source_observations', 'cache_stale', 'confidence')
CANDIDATE_FIELDS += ('association', 'vacancy_evidence', 'extraction_quality', 'purpose_evidence')


def derived_report(page, url):
    candidates = page.get('candidates', [])
    links = list(page.get('fields', {}).get('contact_links', []))
    links += [link['url'] for link in page.get('contact_links', []) if isinstance(link, dict) and link.get('url')]
    return {'version': 1, 'url': page.get('url') or url, 'title': (page.get('title') or '')[:200],
        'vacancy_url': page.get('research_vacancy_url'),
        'employer_excerpt': (page.get('employer_excerpt') or '')[:600],
        'summary': (page.get('text') or page.get('summary') or '')[:1000],
        'outcome': page.get('outcome', 'results'),
        **{k: clean(page[k]) for k in ('upstream_outcome', 'error', 'truncation', 'rendering_signals', 'source_dates') if k in page},
        'stale': bool(page.get('stale')), 'candidates': [clean({k: c[k] for k in CANDIDATE_FIELDS if k in c}) for c in candidates[:100]],
        'contact_links': list(dict.fromkeys(link for link in links if isinstance(link, str) and len(link) <= 2048))[:100]}


def report_read(row, detail=False):
    value = row.report or {}
    stale = bool(value.get('stale') or row.fetched_at and utc_now()-row.fetched_at > timedelta(days=7))
    result = {'id': row.id, 'url': row.url, 'resolved_url': row.resolved_url,
        'title': value.get('title', ''), 'outcome': value.get('outcome', 'pending'),
        'fetched_at': row.fetched_at.replace(tzinfo=timezone.utc) if row.fetched_at else None,
        'stale': stale, 'candidate_count': len(value.get('candidates', []))}
    if detail:
        result['report'] = value
    return result


def list_reports(session, application_id=None, page=1, page_size=20):
    if not 1 <= page or not 1 <= page_size <= 100:
        raise ValueError('page must be positive; page_size must be between 1 and 100')
    query = select(RecipientPageReport).where(RecipientPageReport.fetched_at.is_not(None))
    if application_id:
        get_application(session, application_id)
        query = query.join(RecipientPageUse).where(RecipientPageUse.application_id == application_id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.order_by(RecipientPageReport.fetched_at.desc(), RecipientPageReport.id)
        .offset((page-1)*page_size).limit(page_size))
    return {'items': [report_read(r) for r in rows], 'total': total, 'page': page, 'page_size': page_size}


def get_report(session, report_id, application_id=None):
    if application_id:
        get_application(session, application_id)
        if not session.get(RecipientPageUse, (application_id, report_id)):
            raise ApplicationNotFound('Page report not found for this application')
    row = session.get(RecipientPageReport, report_id)
    if not row or not row.report:
        raise ApplicationNotFound('Page report not found')
    return report_read(row, detail=True)


async def durable_call(function, *args):
    """A cancelled await cannot abandon a SQLite write still executing in a thread."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class PageReports:
    def __init__(self, engine):
        self.engine = engine

    def seeds(self, application_id):
        with Session(self.engine) as session:
            return list(session.scalars(select(RecipientPageReport.url).join(RecipientPageUse)
                .where(RecipientPageUse.application_id == application_id)
                .order_by(RecipientPageUse.used_at.desc()).limit(500)))

    def _associate(self, session, application_id, row, context):
        item = session.get(RecipientPageUse, (application_id, row.id))
        if item is None:
            item = RecipientPageUse(application_id=application_id, report_id=row.id)
            session.add(item)
        item.context = dict(context)
        item.used_at = utc_now()

    def _claim(self, application_id, url, context, allow_fetch, refresh_after, token):
        url = page_key(url)
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            row = session.scalar(select(RecipientPageReport).where(or_(RecipientPageReport.url == url,
                RecipientPageReport.resolved_url == url)).order_by(RecipientPageReport.fetched_at.desc()))
            now = utc_now()
            needs_refresh = bool(row and row.report and refresh_after and row.fetched_at < refresh_after)
            if row and row.report and (not needs_refresh or not allow_fetch):
                self._associate(session, application_id, row, context)
                value = deepcopy(row.report)
                value['stale'] = report_read(row)['stale'] or needs_refresh
                value['fetched_at'] = row.fetched_at.isoformat()+'Z'
                session.commit()
                return 'reused', value
            if row and row.lease_until and row.lease_until > now:
                return 'wait', None
            if not allow_fetch:
                return 'budget', None
            if row is None:
                row = RecipientPageReport(id=hashlib.sha256(url.encode()).hexdigest(), url=url)
                session.add(row)
            row.lease_id, row.lease_until = token, now+timedelta(seconds=45)
            session.commit()
            return 'fetch', row.id

    def _save(self, application_id, report_id, token, context, value):
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            row = session.get(RecipientPageReport, report_id)
            if row.lease_id != token:
                raise RuntimeError('Page report lease expired')
            row.report, row.fetched_at = value, utc_now()
            row.resolved_url = page_key(value['url'])
            row.lease_id = row.lease_until = None
            self._associate(session, application_id, row, context)
            session.commit()

    def _release(self, token):
        with Session(self.engine) as session:
            session.execute(update(RecipientPageReport).where(RecipientPageReport.lease_id == token)
                .values(lease_id=None, lease_until=None))
            session.commit()

    async def page(self, application_id, url, context, fetch, *, allow_fetch=True, refresh_after=None):
        token = str(uuid4())
        try:
            while True:
                state, value = await durable_call(self._claim, application_id, url, context, allow_fetch, refresh_after, token)
                if state == 'reused':
                    return value, False
                if state == 'budget':
                    return None, False
                if state == 'wait':
                    await asyncio.sleep(.15)
                    continue
                report = derived_report(await fetch(), url)
                await durable_call(self._save, application_id, value, token, context, report)
                return report, True
        finally:
            await durable_call(self._release, token)

    def import_legacy(self, path):
        """Offline conversion only. Legacy HTML cache remains untouched and inactive."""
        if not path.exists():
            return 0
        from bs4 import BeautifulSoup
        from webtoolbox.contacts import extract_contacts, extract_contact_links
        from webtoolbox import merge_and_rank
        from webtoolbox.core import rendering_signals
        imported = 0
        with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as cache, Session(self.engine) as session:
            for raw, saved_at in cache.execute("SELECT value,saved_at FROM cache WHERE cache_key LIKE 'page:%' ORDER BY saved_at DESC"):
                value = json.loads(raw)
                url = value.get('final_url')
                if not url or not value.get('html'):
                    continue
                url = page_key(url)
                if session.scalar(select(RecipientPageReport.id).where(or_(RecipientPageReport.url == url, RecipientPageReport.resolved_url == url))):
                    continue
                stamp = datetime.fromtimestamp(saved_at, timezone.utc).replace(tzinfo=None)
                html = value['html']
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.get_text(' ', strip=True) if soup.title else ''
                for node in soup.select('script,style,nav,footer,noscript,svg,form'):
                    node.decompose()
                signals = rendering_signals(html)
                report = derived_report({'url': url, 'title': title, 'text': soup.get_text(' ', strip=True),
                    'outcome': 'rendering_needed' if signals else 'results', 'rendering_signals': signals,
                    'candidates': merge_and_rank(extract_contacts(html, url, fetched_at=stamp.isoformat()+'Z')),
                    'contact_links': extract_contact_links(html, url)}, url)
                row = RecipientPageReport(id=hashlib.sha256(url.encode()).hexdigest(), url=url, resolved_url=url,
                    report=report, fetched_at=stamp)
                session.add(row)
                session.flush()
                imported += 1
            for candidate in session.scalars(select(RecipientCandidate)):
                for url in set(candidate.value.get('source_urls', [])+[candidate.value.get('source_url', '')]):
                    if not url:
                        continue
                    row = session.scalar(select(RecipientPageReport).where(RecipientPageReport.url == page_key(url)))
                    if row:
                        self._associate(session, candidate.application_id, row, candidate.context)
            session.commit()
        return imported


class SearchOnlyCache:
    """Persist search responses; raw HTML is held only briefly in bounded memory."""
    def __init__(self, cache):
        self.cache = cache
        self.pages = OrderedDict()

    def get(self, key, *, allow_stale=False):
        if not key.startswith('page:'):
            return self.cache.get(key, allow_stale=allow_stale)
        entry = self.pages.get(key)
        if not entry or not allow_stale and entry[2] <= time.time():
            return None
        value, saved, expires = entry
        return {**deepcopy(value), 'cached': True, 'fetched_at': saved,
            'cache_age_seconds': max(0, int(time.time()-saved)), 'stale': expires <= time.time()}

    def set(self, key, value, ttl):
        if not key.startswith('page:'):
            return self.cache.set(key, value, ttl)
        self.pages[key] = (deepcopy(value), time.time(), time.time()+ttl)
        self.pages.move_to_end(key)
        while len(self.pages) > 10:
            self.pages.popitem(last=False)

    def stats(self):
        return self.cache.stats()

    def prune(self):
        self.pages.clear()
        return self.cache.prune()
