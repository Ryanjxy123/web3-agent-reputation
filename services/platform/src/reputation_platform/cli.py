"""Local environment diagnostics. No credentials are read or printed."""
import argparse
import importlib.metadata
import json
import shutil
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="reputation")
    parser.add_argument("--version", action="version", version=importlib.metadata.version("reputation-platform"))
    parser.add_argument("command", choices=["doctor"])
    parser.parse_args()
    tools = {name: bool(shutil.which(name)) for name in ("git", "node", "pnpm", "forge", "anvil", "docker", "psql")}
    print(json.dumps({
        "python": ".".join(map(str, sys.version_info[:3])),
        "packages": {name: importlib.metadata.version(name) for name in (
            "reputation-core", "reputation-platform", "reputation-verifier", "pydantic", "fastapi")},
        "tools_on_path": tools,
        "runtime_checks": "NOT_RUN",
    }, indent=2))
    return 0 if all(tools.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
