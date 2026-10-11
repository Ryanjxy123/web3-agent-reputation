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


def test_checkout_eol_attributes_never_change_exported_blob_bytes(tmp_path):
    root = repository(tmp_path, {
        ".gitattributes": "* text eol=crlf\n",
        "README.md": "first line\nsecond line\n",
        "tools.ps1": "Write-Output 'first'\nWrite-Output 'second'\n",
    })
    subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", "true"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.eol", "crlf"], check=True)
    first = package(root, "HEAD", tmp_path / "first")
    second = package(root, "HEAD", tmp_path / "second")
    assert first == second
    assert (tmp_path / "first/source.zip").read_bytes() == (tmp_path / "second/source.zip").read_bytes()
    with zipfile.ZipFile(tmp_path / "first/source.zip") as archive:
        for item in first["files"]:
            original = subprocess.check_output([
                "git", "-C", str(root), "cat-file", "blob", "HEAD:" + item["path"],
            ])
            assert archive.read(item["path"]) == original
            assert b"\r\n" not in original
            assert archive.getinfo(item["path"]).date_time == (1980, 1, 1, 0, 0, 0)


@pytest.mark.parametrize("mode,kind", [("120000", "blob"), ("160000", "commit")])
def test_unsupported_symlink_and_submodule_modes_are_rejected(tmp_path, mode, kind):
    root = repository(tmp_path, {"README.md": "fixture"})
    object_id = subprocess.check_output([
        "git", "-C", str(root), "rev-parse", "HEAD:README.md" if kind == "blob" else "HEAD",
    ], text=True).strip()
    subprocess.run([
        "git", "-C", str(root), "update-index", "--add", "--cacheinfo",
        mode, object_id, "linked",
    ], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Delivery test",
        "-c", "user.email=delivery-test@example.invalid", "commit", "--quiet", "-m", "mode fixture",
    ], check=True)
    with pytest.raises(ValueError, match="unsupported delivery mode"):
        package(root, "HEAD", tmp_path / "output")
    assert not (tmp_path / "output").exists()


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
