"""Human-only import, review and recovery tools. Never replace a live database."""
import json
from pathlib import Path
import shutil
import tempfile
import sqlite3
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app import applications, application_import, application_merge, mail_reviews
from app.activity import record_audit, record_event
from app.backup import backup_workspace, restore_bundle
from app.models import Application, InvalidationEvent
from app.schemas import ApplicationRead
from app.applications import InvalidApplication


class RestoreRequest(BaseModel):
    expected_revision: int = Field(ge=1)


def router():
    route = APIRouter(prefix='/api/workspace')

    def human(request: Request):
        if request.headers.get('authorization') or request.app.state.human_access.connection_owner(request) is None:
            raise HTTPException(403, 'Use the human workspace session for data management')
        return request.app

    def database(app=Depends(human)):
        with Session(app.state.engine) as session:
            yield session

    def changed(session):
        session.add(InvalidationEvent(topic='application.updated'))
        session.commit()

    @route.get('/trash')
    def trash(page: int = Query(1, ge=1), app=Depends(human), session=Depends(database)):
        from sqlalchemy import func
        query = select(Application).where(Application.deleted_at.is_not(None))
        return {'total': session.scalar(select(func.count()).select_from(query.subquery())), 'items': [
            jsonable_encoder(ApplicationRead.model_validate(item)) for item in session.scalars(
                query.order_by(Application.deleted_at.desc(), Application.id).offset((page - 1) * 20).limit(20))]}

    @route.get('/merge/preview')
    def merge_preview(source_id: str, target_id: str, app=Depends(human), session=Depends(database)):
        return application_merge.preview(session, source_id, target_id)

    @route.post('/merge/{target_id}')
    def merge_application(target_id: str, data: application_merge.MergeRequest, app=Depends(human), session=Depends(database)):
        result = application_merge.merge(session, app.state.settings, target_id, data)
        changed(session)
        return result

    @route.post('/trash/{application_id}/restore')
    def restore_application(application_id: str, data: RestoreRequest, app=Depends(human), session=Depends(database)):
        session.execute(text('BEGIN IMMEDIATE'))
        item = session.get(Application, application_id)
        if item is None or item.deleted_at is None:
            raise applications.ApplicationNotFound('Deleted application not found')
        if item.revision != data.expected_revision:
            raise applications.ApplicationRevisionConflict(item, {})
        previous = item.deleted_at
        item.deleted_at = None
        # Restoring history must not flood overdue notices without a human choice.
        item.followup_paused = True
        record_event(session, item.id, 'APPLICATION_RESTORED', 'Application restored; reminders paused for review')
        record_audit(session, item.id, 'APPLICATION', item.id, 'RESTORE', previous={'deleted_at': previous}, new={'deleted_at': None, 'followup_paused': True})
        changed(session)
        return jsonable_encoder(ApplicationRead.model_validate(item))

    @route.get('/mail-reviews')
    def reviews(page: int = Query(1, ge=1), app=Depends(human), session=Depends(database)):
        return mail_reviews.review_page(session, app.state.google, page)

    @route.post('/mail-reviews/{message_id}')
    def review(message_id: str, data: mail_reviews.ReviewDecision, app=Depends(human), session=Depends(database)):
        result = mail_reviews.decide(session, app.state.google, app.state.settings, message_id, data)
        changed(session)
        return result

    async def sheet(file):
        content = await file.read(application_import.MAX_BYTES + 1)
        return file.filename or '', content

    def decoded(value, kind):
        try:
            result = json.loads(value)
            if result is not None and not isinstance(result, kind):
                raise ValueError()
            if isinstance(result, dict) and any(not isinstance(key, str) or not isinstance(item, str) for key, item in result.items()):
                raise ValueError()
            if isinstance(result, list) and any(type(item) is not int or item < 2 for item in result):
                raise ValueError()
            return result
        except (ValueError, TypeError):
            raise InvalidApplication('The import options are invalid. Preview the spreadsheet again.') from None

    @route.post('/imports/preview')
    async def preview(file: UploadFile = File(), mapping: str = Form('null'), app=Depends(human), session=Depends(database)):
        name, content = await sheet(file)
        try:
            import asyncio
            return await asyncio.to_thread(application_import.prepare, session, name, content, decoded(mapping, dict))
        except (ValueError, UnicodeError) as exc:
            raise InvalidApplication(str(exc)) from None

    @route.post('/imports/apply')
    async def import_sheet(file: UploadFile = File(), mapping: str = Form(), selected: str = Form(),
                           duplicates: str = Form('skip'), app=Depends(human), session=Depends(database)):
        name, content = await sheet(file)
        try:
            import asyncio
            result = await asyncio.to_thread(application_import.apply, session, app.state.settings, name, content, decoded(mapping, dict), decoded(selected, list), duplicates)
        except (ValueError, UnicodeError) as exc:
            raise InvalidApplication(str(exc)) from None
        changed(session)
        return result

    @route.post('/backup')
    def download_backup(app=Depends(human)):
        # Uploaded documents are immutable: DB snapshot first, then its referenced
        # files. New uploads commit only after their file has been written.
        folder = Path(tempfile.mkdtemp(prefix='tracker-backup-'))
        try:
            backup_workspace(app.state.settings.app_data_dir, folder / 'workspace')
            archive = folder / 'application-tracker-backup.zip'
            with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
                for path in (folder / 'workspace').rglob('*'):
                    if path.is_file():
                        bundle.write(path, path.relative_to(folder / 'workspace').as_posix())
            return FileResponse(archive, filename=archive.name, background=BackgroundTask(shutil.rmtree, folder))
        except Exception:
            shutil.rmtree(folder)
            raise

    @route.post('/recovery/validate')
    async def validate_recovery(file: UploadFile = File(), app=Depends(human)):
        # Validate/restore in isolation; never activate or overwrite the open workspace.
        import asyncio
        content = await file.read(100 * 1024 * 1024 + 1)
        if len(content) > 100 * 1024 * 1024:
            raise InvalidApplication('Use the recovery command for backups larger than 100 MiB')
        def validate():
            with tempfile.TemporaryDirectory(prefix='tracker-recovery-') as temporary:
                root = Path(temporary)
                archive = root / 'backup.zip'
                archive.write_bytes(content)
                restore_bundle(archive, root / 'restored')
                import sqlite3
                from contextlib import closing
                with closing(sqlite3.connect(root / 'restored' / 'tracker.sqlite3')) as db:
                    count = db.execute('SELECT count(*) FROM applications WHERE deleted_at IS NULL').fetchone()[0]
                return {'valid': True, 'applications': count, 'message': 'Recovery verified in an isolated workspace. Your open workspace was unchanged.'}
        try:
            return await asyncio.to_thread(validate)
        except (ValueError, OSError, KeyError, sqlite3.Error, __import__('zipfile').BadZipFile):
            raise InvalidApplication('This backup could not be verified. Preserve the original and choose a complete tracker backup.') from None

    return route
