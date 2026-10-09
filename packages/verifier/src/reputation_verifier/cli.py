"""Command line entry point for independent bundle verification."""

import argparse
import json
import sys

from .bundle import VerificationError, verify_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reputation-verify")
    parser.add_argument("bundle", help="path to a frozen evidence ZIP")
    parser.add_argument("--rpc-url", "--rpc", dest="rpc_url", help="operator-trusted RPC URL")
    parser.add_argument(
        "--task-rpc-url",
        help="operator-trusted RPC for replaying task chain evidence (defaults to --rpc-url)",
    )
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(args.bundle, rpc_url=args.rpc_url, task_rpc_url=args.task_rpc_url)
    except VerificationError as exc:
        print(json.dumps({"status": "FAIL", "code": exc.code, "message": str(exc)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
