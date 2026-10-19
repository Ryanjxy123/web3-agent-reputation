"""Export or restore public reports and verify retained sources without network access."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import sys
import tarfile
import tempfile
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

import psycopg

from reputation_core.application import normalize_reference
from reputation_platform.db import Repository
from reputation_platform.settings import load_database_url

SCHEMA = "public-reports-package-v1"
INDEX = re.compile(r"runtime/public-reports/[0-9a-f]{32}/package\.json")
DENIED = {"secrets", "platform-config", "platform-postgres", ".git", ".venv", "node_modules"}
PRIVATE_NAME = re.compile(r"secret|password|api[-_]?key|balance[-_](?:before|after)", re.I)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def public_path(name: str) -> str:
    if (not isinstance(name, str) or "\\" in name or ":" in name
        or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError("Package paths must be canonical repository-relative paths")
    path = PurePosixPath(name)
    if (path.is_absolute() or not (name.startswith("runtime/") or name.startswith("configs/")
                                  or name.startswith("docs/adr/"))
        or any(part.startswith(".") or ".private" in part.lower() or part.lower() in DENIED for part in path.parts)
        or PRIVATE_NAME.search(path.name)
        or path.suffix.lower() in {".log", ".db", ".sqlite", ".sqlite3", ".dump", ".key", ".pem", ".p12", ".pfx"}):
        raise ValueError("Package contains a nonpublic or unsupported file path")
    return name


def local_path(root: Path, name: str) -> Path:
    target = root / public_path(name)
    for part in (target, *target.parents):
        if part == root:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError("Package files cannot pass through links or junctions")
    if not target.resolve().is_relative_to(root):
        raise ValueError("Package file escapes its destination")
    return target


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def check_report(repo: Repository, item: dict):
    report = repo._load_report(item["directory"])
    if (report.report_hash != item["report_sha256"] or report.manifest_hash != item["manifest_sha256"]
        or report.registration_reference != item["canonical"] or report.report.candidate_key != item["candidate_key"]
        or report.report.scores.model_dump(mode="json") != item["scores"]
        or report.report.scores.status != "COMPLETE"):
        raise ValueError("Packaged report identity, original bytes or recomputed scores differ")
    return report


def export_package(root: Path, output: Path) -> dict:
    repo = Repository(load_database_url(), root)
    with repo._connect() as connection:
        rows = connection.execute("""SELECT r.*, a.registration_reference FROM reports r
            JOIN agents a ON a.key=r.agent_key
            WHERE r.validated_json->'scores'->>'status'='COMPLETE'
            ORDER BY r.generated_at DESC,r.imported_at DESC,r.id""").fetchall()
    selected = {}
    for row in rows:
        canonical = normalize_reference(row["registration_reference"])
        if canonical is None:
            raise ValueError("A complete database report has no canonical identity")
        selected.setdefault(canonical, row)
    if not selected:
        raise ValueError("The database contains no complete report to publish")
    files, reports = {}, []

    def remember(name: str, expected: str | None = None):
        path = local_path(root, name)
        actual = digest(path)
        if expected is not None and actual != expected:
            raise ValueError("A retained public dependency changed")
        item = {"path": name, "sha256": actual, "size": path.stat().st_size}
        if name in files and files[name] != item:
            raise ValueError("Reports disagree on a shared dependency")
        files[name] = item

    for canonical, row in sorted(selected.items()):
        imported = repo._load_report(row["source_directory"])
        item = {"source_report_id": str(row["id"]), "canonical": canonical,
            "candidate_key": imported.report.candidate_key, "directory": row["source_directory"],
            "name": imported.report.name, "generated_at": imported.report.generated_at.isoformat(),
            "report_sha256": row["report_sha256"], "manifest_sha256": row["manifest_sha256"],
            "scores": row["validated_json"]["scores"]}
        if (imported.registration_reference != canonical or imported.report_hash != item["report_sha256"]
            or imported.manifest_hash != item["manifest_sha256"]
            or imported.report.scores.model_dump(mode="json") != item["scores"]):
            raise ValueError("The retained report differs from its published database record")
        _, dependencies = repo._manifest(imported.directory)
        for name, expected in dependencies.items():
            remember(name, expected)
        for name in ("manifest.json", "report.json", "report.html", "background.json"):
            path = imported.directory / name
            if name == "background.json" and not path.exists():
                continue
            remember(path.relative_to(root).as_posix())
        reports.append(item)
    index_name = f"runtime/public-reports/{secrets.token_hex(16)}/package.json"
    index = {"schema_version": SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
        "reports": reports, "files": [files[name] for name in sorted(files)],
        "source_uuid_is_provenance_only": True, "network_requests": 0}
    index_bytes = json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "x:gz", format=tarfile.PAX_FORMAT) as archive:
        metadata = tarfile.TarInfo(index_name)
        metadata.size, metadata.mode = len(index_bytes), 0o644
        archive.addfile(metadata, io.BytesIO(index_bytes))
        for name, item in sorted(files.items()):
            path = local_path(root, name)
            if digest(path) != item["sha256"]:
                raise ValueError("A source changed while exporting the package")
            metadata = tarfile.TarInfo(name)
            metadata.size, metadata.mode = item["size"], 0o644
            with path.open("rb") as stream:
                archive.addfile(metadata, stream)
    return {"archive": str(output), "archive_sha256": digest(output), "reports": len(reports),
            "files": len(files), "uncompressed_bytes": sum(item["size"] for item in files.values()),
            "archive_bytes": output.stat().st_size, "package_manifest": index_name}


def restore_package(root: Path, supplied: Path, import_db: bool, initialize: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="public-reports-") as temporary:
        staging = Path(temporary).resolve()
        with tarfile.open(supplied, "r:gz") as archive:
            members = archive.getmembers()
            names, folded = set(), set()
            for member in members:
                public_path(member.name)
                if (not member.isfile() or member.issparse() or member.name in names
                    or member.name.casefold() in folded):
                    raise ValueError("Archive members must be unique regular public files")
                names.add(member.name)
                folded.add(member.name.casefold())
            indices = [member for member in members if INDEX.fullmatch(member.name)]
            if len(indices) != 1 or indices[0].size > 32 * 1024 * 1024:
                raise ValueError("Archive requires one bounded public package manifest")
            with archive.extractfile(indices[0]) as stream:
                index = json.load(stream)
            if index.get("schema_version") != SCHEMA or not index.get("reports"):
                raise ValueError("Unsupported or empty public report package")
            inventory = {}
            for item in index["files"]:
                name = public_path(item["path"])
                if (name == indices[0].name or name in inventory or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                    or type(item["size"]) is not int or item["size"] < 0):
                    raise ValueError("Invalid public file inventory")
                inventory[name] = item
            if names != set(inventory) | {indices[0].name}:
                raise ValueError("Archive members differ from the exact package inventory")
            inventory[indices[0].name] = {"size": indices[0].size}
            for member in members:
                if member.size != inventory[member.name]["size"]:
                    raise ValueError("Archive member size differs from its inventory")
                target = local_path(staging, member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
                if member != indices[0] and digest(target) != inventory[member.name]["sha256"]:
                    raise ValueError("Archive member digest differs from its inventory")
        reports = index["reports"]
        identities = set()
        for item in reports:
            UUID(item["source_report_id"])
            public_path(item["directory"] + "/report.json")
            if normalize_reference(item["canonical"]) != item["canonical"] or item["canonical"] in identities:
                raise ValueError("Package reports must represent distinct canonical identities")
            identities.add(item["canonical"])
            check_report(Repository("unused", staging), item)
        missing = []
        for name in inventory:
            target = local_path(root, name)
            staged = local_path(staging, name)
            if target.exists():
                if not target.is_file() or digest(target) != digest(staged):
                    raise ValueError("A local public file conflicts with the package: " + name)
            elif not name.startswith("runtime/"):
                raise ValueError("Required Git configuration or policy is missing: " + name)
            else:
                missing.append((staged, target))
        for staged, target in missing:
            target.parent.mkdir(parents=True, exist_ok=True)
            with staged.open("rb") as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination)
    repo = Repository(load_database_url() if import_db else "unused", root)
    if initialize:
        repo.initialize()
    mappings = []
    for item in reports:
        imported_id = None
        if import_db:
            summary = repo.import_report(item["directory"])
            if summary.scores.model_dump(mode="json") != item["scores"] or summary.candidate_key != item["candidate_key"]:
                raise ValueError("Imported report differs from its authenticated package")
            imported_id = summary.id
        mappings.append({"source_report_id": item["source_report_id"], "imported_report_id": imported_id,
                         "canonical": item["canonical"], "report_sha256": item["report_sha256"]})
    result = {"archive_sha256": digest(supplied), "reports": len(reports), "new_runtime_files": len(missing),
              "database_imported": import_db, "network_requests": 0, "mapping": mappings}
    audit = root / "runtime" / ("public-report-restore-" + secrets.token_hex(16)) / "result.json"
    write_json(audit, result)
    result["result_file"] = audit.relative_to(root).as_posix()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    export = subcommands.add_parser("export", help="Export the real database's latest complete report per identity")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--root", type=Path, default=ROOT)
    for name in ("verify", "import"):
        restore = subcommands.add_parser(name, help="Verify offline and write missing public runtime files; never overwrite conflicts")
        restore.add_argument("archive", type=Path)
        restore.add_argument("--root", type=Path, default=ROOT)
        restore.add_argument("--import", dest="import_db", action="store_true", help="Also import into the configured PostgreSQL database")
        restore.add_argument("--initialize", action="store_true", help="Initialize tables before the explicitly requested database import")
    args = parser.parse_args()
    try:
        if args.command == "export":
            result = export_package(args.root.resolve(), args.output.resolve())
        else:
            import_db = args.command == "import" or args.import_db
            if args.initialize and not import_db:
                parser.error("--initialize requires import or --import")
            result = restore_package(args.root.resolve(), args.archive.resolve(), import_db, args.initialize)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except psycopg.Error:
        print("PostgreSQL operation failed; credentials are not printed.", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print("Public report operation failed: " + type(error).__name__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
