"""Admission policy, durable snapshots and retention for the native gateway."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tarfile
import tempfile
import time
from uuid import uuid4

POLICY = dict(
    max_upload_bytes=256 * 1024**2,
    max_result_bytes=1024 * 1024**2,
    max_document_pages=5000,
    max_documents_per_request=32,
    max_pending_documents=40,
    max_pending_pages=4800,
    min_free_bytes=10 * 1024**3,
    max_concurrent_uploads=4,
    intermediate_days=7,
    diagnostic_days=14,
    backup_copies=14,
)
JOB_ID = re.compile(r"^[0-9a-f]{32}$")


class AdmissionError(ValueError):
    def __init__(self, message, status=429):
        super().__init__(message)
        self.status = status


def sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def durable_replace(source, destination):
    with source.open("r+b") as stream:
        os.fsync(stream.fileno())
    source.replace(destination)
    sync_directory(destination.parent)


def policy(values=None):
    values = values or {}
    if not isinstance(values, dict) or set(values) - POLICY.keys():
        raise ValueError("Unknown production policy setting")
    result = POLICY | values
    if any(type(value) is not int or value <= 0 for value in result.values()):
        raise ValueError("Production limits must be positive integers")
    return result


def inspect_pdf(path, maximum):
    import pymupdf

    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf or document.needs_pass or not document.page_count:
                raise ValueError("Expected a nonempty, unencrypted PDF")
            count = document.page_count
    except (pymupdf.FileDataError, RuntimeError) as error:
        raise ValueError("Invalid or unreadable PDF") from error
    if count > maximum:
        raise AdmissionError("PDF exceeds the configured page limit", 413)
    return count


def capacity(db, root, limits, documents, pages, size):
    if (
        documents > limits["max_pending_documents"]
        or pages > limits["max_pending_pages"]
    ):
        raise AdmissionError("Submission exceeds the queue capacity", 413)
    row = db.execute(
        """SELECT count(*) AS documents,
        COALESCE(sum(COALESCE(json_extract(t.details,'$.page_count'),?)),0) AS pages,
        COALESCE(sum(COALESCE(json_extract(t.details,'$.source_bytes'),0)),0) AS input_bytes
        FROM jobs j JOIN task_state t USING(id)
        WHERE j.status IN ('queued','running') AND t.kind IN ('book','legacy')""",
        (limits["max_document_pages"],),
    ).fetchone()
    if (
        row["documents"] + documents > limits["max_pending_documents"]
        or row["pages"] + pages > limits["max_pending_pages"]
    ):
        raise AdmissionError("Queue capacity reached; retry later")
    reserved = max((row["input_bytes"] + size) * 12, (row["pages"] + pages) * 1024**2)
    if shutil.disk_usage(root).free < limits["min_free_bytes"] + reserved:
        raise AdmissionError("Gateway disk reserve reached; retry later", 503)


def storage_status(queue):
    with queue.connect() as db:
        active = db.execute(
            """SELECT count(*) AS documents,COALESCE(sum(COALESCE(json_extract(t.details,'$.page_count'),?)),0) AS pages
            FROM jobs j JOIN task_state t USING(id)
            WHERE j.status IN ('queued','running') AND t.kind IN ('book','legacy')""",
            (queue.production["max_document_pages"],),
        ).fetchone()
        last = db.execute(
            "SELECT value FROM operations WHERE name=?", ("backup",)
        ).fetchone()
        cleanup = db.execute(
            "SELECT value FROM operations WHERE name=?", ("cleanup",)
        ).fetchone()
    return dict(
        policy=queue.production,
        pending=dict(active),
        free_bytes=shutil.disk_usage(queue.root).free,
        backup=json.loads(last["value"]) if last else None,
        cleanup=json.loads(cleanup["value"]) if cleanup else None,
    )


def snapshot(queue, destination, config_path=None):
    """Pin immutable payloads with hard links while holding the SQLite writer lock."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix=".snapshot-", dir=queue.root) as temporary:
        stage = Path(temporary)
        with queue.connect() as lock:
            lock.execute("BEGIN IMMEDIATE")
            with (
                closing(sqlite3.connect(queue.database)) as source,
                closing(sqlite3.connect(stage / "queue.sqlite3")) as target,
            ):
                source.backup(target)
            ids = [row["id"] for row in lock.execute("SELECT id FROM jobs")]
            for job_id in ids:
                for name in ("input.pdf", "result.tar.gz"):
                    source = queue.root / job_id / name
                    if source.is_file():
                        target = stage / job_id / name
                        target.parent.mkdir(exist_ok=True)
                        os.link(source, target)
        if config_path is not None:
            config = json.loads(Path(config_path).read_text(encoding="utf-8"))
            config["production"] = queue.production
            config.update(queue.settings)
            (stage / "gateway.json").write_text(
                json.dumps(config, indent=2), encoding="utf-8"
            )
            (stage / "gateway.json").chmod(0o600)
        entries = {}
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                with path.open("rb") as stream:
                    entries[path.relative_to(stage).as_posix()] = dict(
                        size=path.stat().st_size,
                        sha256=hashlib.file_digest(stream, "sha256").hexdigest(),
                    )
        manifest = dict(format=1, created=time.time(), files=entries)
        if shutil.disk_usage(destination).free < queue.production[
            "min_free_bytes"
        ] + sum(item["size"] for item in entries.values()):
            raise AdmissionError("Backup disk reserve reached", 503)
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        name = (
            time.strftime("gateway-%Y%m%dT%H%M%SZ", time.gmtime())
            + "-"
            + uuid4().hex[:8]
            + ".tar"
        )
        target = destination / name
        incoming = destination / (name + ".incoming")
        try:
            with tarfile.open(incoming, "w") as archive:
                for path in sorted(stage.rglob("*")):
                    if path.is_file():
                        archive.add(
                            path,
                            arcname=path.relative_to(stage).as_posix(),
                            recursive=False,
                        )
            incoming.chmod(0o600)
            with incoming.open("r+b") as stream:
                os.fsync(stream.fileno())
            incoming.replace(target)
            sync_directory(destination)
        finally:
            incoming.unlink(missing_ok=True)
    summary = dict(
        created=manifest["created"],
        name=name,
        bytes=target.stat().st_size,
        files=len(entries),
        replicated=False,
    )
    with queue.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO operations VALUES (?,?)",
            ("backup", json.dumps(summary)),
        )
    return target


def restore(archive_path, destination):
    """Verify a backup into a new directory and fence all pre-backup attempts."""
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Restore destination must be a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".restore-", dir=destination.parent
    ) as temporary:
        stage = Path(temporary)
        with tarfile.open(archive_path, "r:") as archive:
            members = archive.getmembers()
            size = sum(member.size for member in members)
            if (
                size > Path(archive_path).stat().st_size
                or size > shutil.disk_usage(stage).free
            ):
                raise ValueError("Backup size exceeds available storage")
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate backup entries")
            for member in members:
                parts = Path(member.name).parts
                if (
                    not member.isfile()
                    or Path(member.name).is_absolute()
                    or ".." in parts
                    or "\\" in member.name
                    or Path(member.name).as_posix() != member.name
                ):
                    raise ValueError("Invalid backup path")
                if member.name not in (
                    "manifest.json",
                    "queue.sqlite3",
                    "gateway.json",
                ) and not (
                    len(parts) == 2
                    and JOB_ID.fullmatch(parts[0])
                    and parts[1] in ("input.pdf", "result.tar.gz")
                ):
                    raise ValueError("Unexpected backup entry")
                target = stage / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
        manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("format") != 1 or set(names) != (
            set(manifest["files"]) | {"manifest.json"}
        ):
            raise ValueError("Backup manifest differs from archive")
        for name, expected in manifest["files"].items():
            path = stage / name
            with path.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            if (
                checksum != expected["sha256"]
                or path.stat().st_size != expected["size"]
            ):
                raise ValueError("Backup checksum mismatch for " + name)
        with closing(sqlite3.connect(stage / "queue.sqlite3")) as db, db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database integrity check failed")
            now = time.time()
            db.execute(
                """INSERT OR REPLACE INTO manual_retries
                SELECT j.id,t.attempts,? FROM jobs j JOIN task_state t USING(id)
                WHERE j.status IN ('queued','running')""",
                (now,),
            )
            db.execute(
                "UPDATE attempts SET status='interrupted',finished=?,error='Restored from backup' WHERE status='running'",
                (now,),
            )
            db.execute(
                "UPDATE jobs SET status='queued',node='',updated=?,error='Restored from backup' WHERE status='running'",
                (now,),
            )
            db.execute(
                "UPDATE task_state SET lease='',started=0,queued=?,available=? WHERE id IN (SELECT id FROM jobs WHERE status='queued')",
                (now, now),
            )
            db.execute("DELETE FROM nodes")
            db.execute("DELETE FROM node_state")
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='admin_sessions'"
            ).fetchone():
                db.execute("DELETE FROM admin_sessions")
        (stage / "manifest.json").unlink()
        if (stage / "gateway.json").exists():
            config = json.loads((stage / "gateway.json").read_text(encoding="utf-8"))
            config["data_dir"] = str(destination.resolve())
            (stage / "gateway.json").write_text(
                json.dumps(config, indent=2), encoding="utf-8"
            )
            (stage / "gateway.json").chmod(0o600)
        stage.chmod(0o700)
        stage.replace(destination)
        sync_directory(destination.parent)
    return dict(
        destination=str(destination),
        restored_at=time.time(),
        files=len(manifest["files"]),
    )


def cleanup(queue):
    now = time.time()
    removed = []
    with queue.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        roots = db.execute("""SELECT j.id,j.status,j.updated FROM jobs j JOIN task_state t USING(id)
            WHERE t.parent='' AND j.status IN ('done','failed','cancelled')""").fetchall()
        for root in roots:
            days = (
                queue.production["intermediate_days"]
                if root["status"] == "done"
                else queue.production["diagnostic_days"]
            )
            if now - root["updated"] < days * 86400:
                continue
            children = db.execute(
                """WITH RECURSIVE tree(id) AS (SELECT ? UNION ALL
                SELECT t.id FROM task_state t JOIN tree ON t.parent=tree.id)
                SELECT j.id,j.status,t.kind FROM jobs j JOIN task_state t USING(id)
                WHERE j.id IN (SELECT id FROM tree) AND t.kind IN ('prepare','extract','merge')""",
                (root["id"],),
            ).fetchall()
            for child in children:
                for name in ("input.pdf", "result.tar.gz"):
                    path = queue.root / child["id"] / name
                    if path.is_file():
                        path.unlink()
                        removed.append(str(path.relative_to(queue.root)))
                db.execute(
                    "INSERT OR REPLACE INTO purged_artifacts VALUES (?,?)",
                    (child["id"], now),
                )
        summary = dict(finished=now, removed_files=len(removed))
        db.execute(
            "INSERT OR REPLACE INTO operations VALUES (?,?)",
            ("cleanup", json.dumps(summary)),
        )
    return summary


def confirm_replica(queue, name, checksum, host):
    if not re.fullmatch(
        r"gateway-\d{8}T\d{6}Z-[0-9a-f]{8}\.tar", name
    ) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("Invalid backup receipt")
    with queue.connect() as db:
        row = db.execute("SELECT value FROM operations WHERE name='backup'").fetchone()
        value = json.loads(row["value"]) if row else {}
        if value.get("name") != name:
            raise ValueError("Backup receipt does not match the latest snapshot")
        value.update(
            replicated=True, replica_host=host, sha256=checksum, verified_at=time.time()
        )
        db.execute(
            "INSERT OR REPLACE INTO operations VALUES (?,?)",
            ("backup", json.dumps(value)),
        )
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("config")
    backup.add_argument("destination")
    recover = sub.add_parser("restore")
    recover.add_argument("archive")
    recover.add_argument("destination")
    clean = sub.add_parser("cleanup")
    clean.add_argument("config")
    receipt = sub.add_parser("confirm-replica")
    receipt.add_argument("config")
    receipt.add_argument("name")
    receipt.add_argument("checksum")
    receipt.add_argument("host")
    args = parser.parse_args()
    if args.action == "restore":
        print(json.dumps(restore(args.archive, args.destination)))
        return
    from aih_contexture.scripts.cluster_gateway import Queue

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    queue = Queue(Path(config["data_dir"]), production=config.get("production"))
    if args.action == "backup":
        print(snapshot(queue, args.destination, args.config))
    elif args.action == "cleanup":
        print(json.dumps(cleanup(queue)))
    else:
        print(json.dumps(confirm_replica(queue, args.name, args.checksum, args.host)))


if __name__ == "__main__":
    main()
