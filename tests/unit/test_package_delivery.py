"""Source delivery must use committed public files and never local runtime bytes."""

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts.package_delivery import package


def repository(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Delivery test",
        "-c", "user.email=delivery-test@example.invalid", "commit", "--quiet", "-m", "fixture",
    ], check=True)
    return root


def test_exact_commit_archive_and_deterministic_manifests(tmp_path):
    root = repository(tmp_path, {"README.md": "committed", ".env.example": "TOKEN=example"})
    (root / "README.md").write_text("dirty local text", encoding="utf-8")
    (root / "runtime").mkdir()
    (root / "runtime/secret.json").write_text("secret", encoding="utf-8")
    first = package(root, "HEAD", tmp_path / "first")
    second = package(root, "HEAD", tmp_path / "second")
    assert first == second
    with zipfile.ZipFile(tmp_path / "first/source.zip") as archive:
        assert archive.read("README.md") == b"committed"
        assert "runtime/secret.json" not in archive.namelist()
    assert first["acceptance_status"] == "NOT_ASSERTED"
    licenses = json.loads((tmp_path / "first/licenses.json").read_text(encoding="utf-8"))
    assert licenses["first_party_license"] == "NOT_DECLARED"


@pytest.mark.parametrize("name", [".env", "runtime/config.json", "private.key", ".ENV", "Runtime/config.json"])
def test_ref_with_secret_or_runtime_path_is_rejected_before_output(tmp_path, name):
    root = repository(tmp_path, {name: "must not publish"})
    with pytest.raises(ValueError, match="prohibited delivery path"):
        package(root, "HEAD", tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_existing_output_is_preserved(tmp_path):
    root = repository(tmp_path, {"README.md": "fixture"})
    output = tmp_path / "output"
    output.mkdir()
    marker = output / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        package(root, "HEAD", output)
    assert marker.read_text(encoding="utf-8") == "keep"
