"""Portable database/document backups. Stop the app before copying documents."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import sqlite3
from datetime import datetime, timezone


def checksum(path: Path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def no_symlinks(folder: Path):
    if folder.is_symlink() or any(path.is_symlink() for path in folder.rglob("*")):
        raise ValueError("Document backups cannot contain symbolic links")


def backup_workspace(data_dir: Path, target: Path) -> dict:
    data_dir, target = data_dir.resolve(), target.resolve()
    source = data_dir / "tracker.sqlite3"
    if not source.is_file():
        raise ValueError("Tracker database not found")
    if target == data_dir or data_dir in target.parents:
        raise ValueError("Choose a backup directory outside the application data directory")
    target.mkdir(parents=True, exist_ok=False)
    database = target / "tracker.sqlite3"
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(database) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
    if (data_dir / "documents").exists():
        no_symlinks(data_dir / "documents")
        shutil.copytree(data_dir / "documents", target / "documents")
    metadata = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "source_data_dir": str(data_dir),
                "source_platform": os.name, "database_sha256": checksum(database)}
    (target / "backup.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def restore_workspace(source: Path, data_dir: Path):
    source, data_dir = source.resolve(), data_dir.resolve()
    metadata = json.loads((source / "backup.json").read_text(encoding="utf-8"))
    if metadata.get("version") != 1 or metadata.get("source_platform") not in {"nt", "posix"}:
        raise ValueError("Unsupported backup format")
    database = source / "tracker.sqlite3"
    if checksum(database) != metadata["database_sha256"]:
        raise ValueError("Backup database checksum does not match")
    if data_dir.exists() and any(data_dir.iterdir()):
        raise ValueError("Restore requires an empty data directory; existing records are never overwritten")
    data_dir.mkdir(parents=True, exist_ok=True)
    if (source / "documents").exists():
        no_symlinks(source / "documents")
        shutil.copytree(source / "documents", data_dir / "documents")
    target = data_dir / "tracker.sqlite3"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup database integrity check failed")
        tables = {row[0] for row in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "application_documents" in tables:
            old_path = PureWindowsPath if metadata["source_platform"] == "nt" else PurePosixPath
            old_root = old_path(metadata["source_data_dir"]) / "documents"
            for doc_id, stored in dst.execute("SELECT id, storage_path FROM application_documents WHERE storage_path IS NOT NULL").fetchall():
                try:
                    relative = old_path(stored).relative_to(old_root)
                except ValueError as exc:
                    raise ValueError("A document path is outside the backed-up workspace") from exc
                relocated = (data_dir / "documents" / Path(*relative.parts)).resolve()
                if ".." in relative.parts or not relocated.is_relative_to(data_dir / "documents") or not relocated.is_file():
                    raise ValueError("A referenced document is missing or has an unsafe path")
                dst.execute("UPDATE application_documents SET storage_path=? WHERE id=?", (str(relocated), doc_id))
        if "human_sessions" in tables:
            dst.execute("DELETE FROM human_sessions")
        if "push_deliveries" in tables:
            dst.execute("DELETE FROM push_deliveries")
        if "push_devices" in tables:
            dst.execute("DELETE FROM push_devices")
        if "login_attempts" in tables:
            dst.execute("DELETE FROM login_attempts")
        dst.commit()


def run():
    parser = argparse.ArgumentParser(description="Back up/restore the workspace. Stop the application first.")
    commands = parser.add_subparsers(dest="operation", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True, help="New backup directory")
    restore = commands.add_parser("restore")
    restore.add_argument("--source", type=Path, required=True)
    restore.add_argument("--data-dir", type=Path, required=True, help="Empty destination")
    args = parser.parse_args()
    try:
        if args.operation == "backup":
            from app.config import Settings
            backup_workspace(Settings().app_data_dir, args.output)
            print(f"Backup created: {args.output}")
        else:
            restore_workspace(args.source, args.data_dir)
            print(f"Workspace restored: {args.data_dir}. Start the app to apply migrations; sign in again.")
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    run()
