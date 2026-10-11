"""Export exact committed source bytes, checksums and a license audit inventory."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_DIRS = {".git", "runtime", "secrets", "artifacts", "node_modules", ".venv"}
BLOCKED_SUFFIXES = {".key", ".pem", ".sqlite", ".sqlite3", ".db"}


def git(root: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *arguments])


def package(root: Path, ref: str, output: Path) -> dict:
    commit = git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    paths = git(root, "ls-tree", "-rz", "--name-only", commit).decode().split("\0")[:-1]
    for name in paths:
        path = PurePosixPath(name)
        lowered_parts = {part.lower() for part in path.parts}
        lowered_name = path.name.lower()
        if (
            not path.parts or path.is_absolute() or ".." in path.parts
            or BLOCKED_DIRS.intersection(lowered_parts) or path.suffix.lower() in BLOCKED_SUFFIXES
            or (lowered_name.startswith(".env") and lowered_name != ".env.example")
            or lowered_name in {"setup-secrets.json", "publisher-secret.json"}
        ):
            raise ValueError(f"Ref contains a prohibited delivery path: {name}")
    if output.exists():
        raise FileExistsError("Delivery output must not already exist")
    output.mkdir(parents=True)
    archive = output / "source.zip"
    git(root, "archive", "--format=zip", "--output=" + str(archive.resolve()), commit)
    with zipfile.ZipFile(archive) as source:
        files: list[dict[str, Any]] = [
            {"path": name, "byte_count": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name in sorted(source.namelist()) if not name.endswith("/")
            for data in [source.read(name)]
        ]
    manifest = {
        "schema_version": "delivery-source-v1",
        "commit": commit,
        "source_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": files,
        "acceptance_status": "NOT_ASSERTED",
        "anonymous_submission_status": "NOT_REVIEWED",
    }
    notices = [item for item in files if any(
        marker in PurePosixPath(item["path"]).name.lower()
        for marker in ("license", "notice", "upstream_readme")
    )]
    licenses = {
        "schema_version": "delivery-license-inventory-v1",
        "commit": commit,
        "first_party_license": "PRESENT" if any(
            item["path"].lower().startswith("license") for item in files
        ) else "NOT_DECLARED",
        "notice_files": notices,
        "dependency_license_review": "NOT_REVIEWED",
        "dependency_locks": [item for item in files if item["path"] in {
            "uv.lock", "apps/web/pnpm-lock.yaml", "configs/upstream-lock.json"
        }],
    }
    for name, value in (("manifest.json", manifest), ("licenses.json", licenses)):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="exact commit/ref to export")
    parser.add_argument("--output", type=Path, required=True, help="new local output directory")
    args = parser.parse_args()
    manifest = package(ROOT, args.ref, args.output)
    print(json.dumps({"commit": manifest["commit"], "file_count": len(manifest["files"])}))


if __name__ == "__main__":
    main()
