"""Fail-fast checks for actual source. Requires real PostgreSQL; never skips it."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    commands = [
        ["uv", "run", "--all-packages", "ruff", "check", "packages", "services", "fixtures/agents", "tests", "scripts"],
        ["uv", "run", "--all-packages", "mypy", "-p", "reputation_core", "-p", "reputation_platform", "-p", "reputation_verifier", "-p", "fixture_agents"],
        ["uv", "run", "--all-packages", "python", "scripts/generate_schemas.py", "--check"],
        ["uv", "run", "--all-packages", "pytest", "-q"],
        ["pnpm", "--dir", "apps/web", "generate:types"],
        ["git", "diff", "--exit-code", "--", "packages/schemas/generated", "apps/web/src/api/generated"],
        ["pnpm", "--dir", "apps/web", "build"],
        ["pnpm", "--dir", "apps/web", "test"],
        ["forge", "test", "--root", "contracts"],
    ]
    env = {**os.environ, "FAIL_ON_SKIP": "1"}
    for command in commands:
        executable = shutil.which(command[0])
        if executable is None:
            print(f"Required tool missing: {command[0]}", flush=True)
            return 1
        print("CHECK " + " ".join(command), flush=True)
        result = subprocess.run([executable, *command[1:]], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
