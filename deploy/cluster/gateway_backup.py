"""Daily gateway snapshot and verified off-host replication using existing SSH."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

NAME = re.compile(r"^gateway-\d{8}T\d{6}Z-[0-9a-f]{8}\.tar$")


def run(arguments):
    return subprocess.check_output(arguments, text=True).strip()


def checksum(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def prune(directory, copies):
    files = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and not path.is_symlink() and NAME.fullmatch(path.name)
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files[copies:]:
        path.unlink()
        path.with_suffix(".sha256").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "pull", "confirm", "latest"])
    parser.add_argument("config")
    parser.add_argument("--name")
    parser.add_argument("--checksum")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    directory = Path(config["backup_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    if args.action == "pull":
        remote = [config.get("source_python", "python3"), config["source_script"]]
        ssh = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            config["source_host"],
        ]
        value = json.loads(run(ssh + remote + ["latest", config["source_config"]]))
        name = value["name"]
        if not NAME.fullmatch(name):
            raise ValueError("Invalid backup name from source")
        existing = directory / name
        if existing.exists() and checksum(existing) == value["sha256"]:
            run(
                ssh
                + remote
                + [
                    "confirm",
                    config["source_config"],
                    "--name",
                    name,
                    "--checksum",
                    value["sha256"],
                ]
            )
            print(json.dumps(value | dict(replicated=True, reused=True)))
            return
        if shutil.disk_usage(directory).free < value["bytes"] + 10 * 1024**3:
            raise RuntimeError("Replica disk reserve reached")
        incoming = directory / (name + ".incoming")
        try:
            subprocess.run(
                [
                    "scp",
                    "-q",
                    config["source_host"]
                    + ":"
                    + config["source_backup_dir"]
                    + "/"
                    + name,
                    str(incoming),
                ],
                check=True,
            )
            if (
                incoming.stat().st_size != value["bytes"]
                or checksum(incoming) != value["sha256"]
            ):
                raise RuntimeError("Replica checksum mismatch")
            incoming.chmod(0o600)
            with incoming.open("r+b") as stream:
                os.fsync(stream.fileno())
            incoming.replace(directory / name)
            (directory / name).with_suffix(".sha256").write_text(
                value["sha256"] + "  " + name + "\n"
            )
            run(
                ssh
                + remote
                + [
                    "confirm",
                    config["source_config"],
                    "--name",
                    name,
                    "--checksum",
                    value["sha256"],
                ]
            )
            prune(directory, config.get("copies", 14))
            print(json.dumps(value | dict(replicated=True)))
        finally:
            incoming.unlink(missing_ok=True)
        return
    if args.action == "latest":
        files = sorted(
            path
            for path in directory.iterdir()
            if path.is_file() and NAME.fullmatch(path.name)
        )
        if not files or time.time() - files[-1].stat().st_mtime > 36 * 3600:
            raise RuntimeError("No recent local gateway backup")
        latest = files[-1]
        print(
            json.dumps(
                dict(
                    name=latest.name,
                    sha256=checksum(latest),
                    bytes=latest.stat().st_size,
                )
            )
        )
        return
    docker = [
        "docker",
        "exec",
        config["container"],
        "python",
        "-m",
        "aih_contexture.scripts.cluster_production",
    ]
    if args.action == "create":
        run(docker + ["cleanup", "/app/config.json"])
        source = run(docker + ["backup", "/app/config.json", "/data/backup-export"])
        name = Path(source).name
        if (
            not NAME.fullmatch(name)
            or Path(source).parent.as_posix() != "/data/backup-export"
        ):
            raise ValueError("Unexpected snapshot path")
        destination = directory / name
        incoming = directory / (name + ".incoming")
        try:
            size = int(
                run(
                    [
                        "docker",
                        "exec",
                        config["container"],
                        "python",
                        "-c",
                        "from pathlib import Path; import sys; print(Path(sys.argv[1]).stat().st_size)",
                        source,
                    ]
                )
            )
            if shutil.disk_usage(directory).free < size + 10 * 1024**3:
                raise RuntimeError("Local backup disk reserve reached")
            subprocess.run(
                ["docker", "cp", config["container"] + ":" + source, str(incoming)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            incoming.chmod(0o600)
            with incoming.open("r+b") as stream:
                os.fsync(stream.fileno())
            digest = checksum(incoming)
            incoming.replace(destination)
            destination.with_suffix(".sha256").write_text(digest + "  " + name + "\n")
            prune(directory, config.get("copies", 14))
        finally:
            incoming.unlink(missing_ok=True)
            subprocess.run(
                [
                    "docker",
                    "exec",
                    config["container"],
                    "python",
                    "-c",
                    'from pathlib import Path; import sys; p=Path(sys.argv[1]); assert p.parent==Path("/data/backup-export"); p.unlink()',
                    source,
                ],
                check=True,
            )
        print(
            json.dumps(dict(name=name, sha256=digest, bytes=destination.stat().st_size))
        )
        return
    if (
        not args.name
        or not NAME.fullmatch(args.name)
        or checksum(directory / args.name) != args.checksum
    ):
        raise ValueError("Invalid replica confirmation")
    run(
        docker
        + [
            "confirm-replica",
            "/app/config.json",
            args.name,
            args.checksum,
            config["replica_host"],
        ]
    )
    prune(directory, config.get("copies", 14))
    print(json.dumps(dict(name=args.name, confirmed=True)))


if __name__ == "__main__":
    main()
