import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_core_has_no_io_framework_imports():
    forbidden = {"fastapi", "sqlalchemy", "httpx", "web3", "requests", "os", "subprocess"}
    for file in (ROOT / "packages/core/src").rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            assert not forbidden.intersection(m.split(".")[0] for m in modules), str(file)


def test_verifier_does_not_import_platform():
    for file in (ROOT / "packages/verifier/src").rglob("*.py"):
        assert "reputation_platform" not in file.read_text(encoding="utf-8")
