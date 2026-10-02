"""Local environment diagnostics. No credentials are read or printed."""

import argparse
import asyncio
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="reputation")
    parser.add_argument(
        "--version", action="version", version=importlib.metadata.version("reputation-platform")
    )
    parser.add_argument("command", choices=["doctor", "migrate", "worker", "deploy-local", "seed"])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument(
        "--runtime-dir", help="Local setup directory inside this repository's runtime folder"
    )
    args = parser.parse_args()
    if args.command in {"deploy-local", "seed"}:
        from reputation_platform.application.local_deploy import deploy
        from reputation_platform.infrastructure.db.connection import repo_root

        root = repo_root()
        runtime = (
            (root / Path(args.runtime_dir)).resolve()
            if args.runtime_dir
            else root / "runtime/local-chain"
        )
        if not runtime.is_relative_to((root / "runtime").resolve()):
            parser.error("--runtime-dir must stay inside the repository runtime folder")
        deployment = deploy(root, args.rpc_url, runtime)
        if args.command == "seed":
            from reputation_platform.application.local_seed import seed

            seed(root, deployment, runtime)
        print(
            json.dumps(
                {
                    "status": "LOCAL_DEPLOYMENT_READY"
                    if args.command == "deploy-local"
                    else "LOCAL_FIXTURES_SEEDED",
                    "chain_instance": deployment.chain.instance_hash,
                    "registry": deployment.registry.address,
                    "record": deployment.record.address,
                    "anchor": deployment.anchor.address,
                },
                indent=2,
            )
        )
        return 0
    if args.command == "worker":
        from reputation_platform.worker.main import serve

        asyncio.run(serve(args.once))
        return 0
    if args.command == "migrate":
        from alembic import command
        from alembic.config import Config

        from reputation_platform.infrastructure.db.connection import repo_root

        command.upgrade(Config(str(repo_root() / "alembic.ini")), "head")
        print("Database migrations are at head.")
        return 0
    tools = {
        name: bool(shutil.which(name))
        for name in ("git", "node", "pnpm", "forge", "anvil", "docker", "psql")
    }
    print(
        json.dumps(
            {
                "python": ".".join(map(str, sys.version_info[:3])),
                "packages": {
                    name: importlib.metadata.version(name)
                    for name in (
                        "reputation-core",
                        "reputation-platform",
                        "reputation-verifier",
                        "pydantic",
                        "fastapi",
                    )
                },
                "tools_on_path": tools,
                "runtime_checks": "NOT_RUN",
            },
            indent=2,
        )
    )
    return 0 if all(tools.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
