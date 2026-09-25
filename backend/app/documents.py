from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activity import record_audit, record_event
from app.applications import ApplicationNotFound, InvalidApplication, get_application
from app.models import ActorType, ApplicationDocument, DocumentType


def _clean_filename(value: str | None) -> str:
    filename = Path((value or "").replace("\\", "/")).name.strip()
    if not filename or filename in {".", ".."}:
        raise InvalidApplication("Provide a document filename")
    if len(filename) > 500:
        raise InvalidApplication("Document filename must be 500 characters or fewer")
    return filename


def list_documents(session: Session, application_id: str) -> list[ApplicationDocument]:
    get_application(session, application_id)
    return list(session.scalars(
        select(ApplicationDocument)
        .where(ApplicationDocument.application_id == application_id)
        .order_by(ApplicationDocument.created_at.desc(), ApplicationDocument.id.desc())
    ))


def create_document(
    session: Session,
    application_id: str,
    document_type: DocumentType,
    data_dir: Path,
    *,
    upload: UploadFile | None = None,
    filename: str | None = None,
    external_reference: str | None = None,
    actor_type: ActorType = ActorType.HUMAN,
    actor_reference: str | None = None,
) -> ApplicationDocument:
    get_application(session, application_id)
    reference = external_reference.strip() if external_reference else None
    has_upload = upload is not None and bool(upload.filename)
    if has_upload == bool(reference):
        raise InvalidApplication("Provide either one uploaded file or one external/local reference")

    display_name = _clean_filename(upload.filename if has_upload else filename)
    stored_path: Path | None = None
    if has_upload:
        directory = (data_dir / "documents" / application_id).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        stored_path = directory / f"{uuid4().hex}_{display_name}"
        try:
            with stored_path.open("wb") as destination:
                while chunk := upload.file.read(1024 * 1024):
                    destination.write(chunk)
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise

    document = ApplicationDocument(
        application_id=application_id,
        type=document_type,
        filename=display_name,
        storage_path=str(stored_path) if stored_path else None,
        external_reference=reference,
    )
    session.add(document)
    session.flush()
    record_event(
        session, application_id, "DOCUMENT_ATTACHED", f"{document_type.value.replace('_', ' ').title()} attached: {display_name}",
        actor_type=actor_type, actor_reference=actor_reference, metadata={"document_id": document.id},
    )
    record_audit(
        session, application_id, "DOCUMENT", document.id, "CREATE",
        new={"type": document_type.value, "filename": display_name, "external_reference": reference, "uploaded": has_upload},
        actor_type=actor_type, actor_reference=actor_reference,
    )
    try:
        session.commit()
    except Exception:
        if stored_path:
            stored_path.unlink(missing_ok=True)
        raise
    session.refresh(document)
    return document


def get_document(session: Session, application_id: str, document_id: str) -> ApplicationDocument:
    get_application(session, application_id)
    document = session.scalar(select(ApplicationDocument).where(
        ApplicationDocument.id == document_id,
        ApplicationDocument.application_id == application_id,
    ))
    if document is None:
        raise ApplicationNotFound("Document not found for this application")
    return document


def uploaded_path(session: Session, application_id: str, document_id: str, data_dir: Path) -> tuple[Path, str]:
    document = get_document(session, application_id, document_id)
    if not document.storage_path:
        raise ApplicationNotFound("This document is a reference and has no uploaded file")
    root = (data_dir / "documents").resolve()
    path = Path(document.storage_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ApplicationNotFound("Uploaded document file not found")
    return path, document.filename
