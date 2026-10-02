"""Check delivered reference logic, JSON parsing, required files and UTF-8.
This is not a replacement for integration/security/chain tests.
"""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    for name in ("AGENTS.md", "PLAN.md", "docs/implementation/BACKLOG.md", "docs/implementation/STATUS.md", "configs/policies/policy-v1.json"):
        if not (ROOT / name).is_file():
            print(f"Missing required file: {name}", file=sys.stderr)
            return 2
    for folder in ("configs", "fixtures/datasets"):
        for path in (ROOT / folder).rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
    print("Bootstrap/reference checks only; live platform tests are NOT_RUN.", flush=True)
    return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/reference", "-v"], cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
