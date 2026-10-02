"""Read-only local Git inspection. No fetch, init, config changes, commits or push."""
from __future__ import annotations

import argparse
from pathlib import Path
import os
import re
import shutil
import subprocess
from urllib.parse import urlsplit, urlunsplit

EXPECTED = "ryanjxy123/web3-agent-reputation"


def sanitize_remote(value: str) -> str:
    if "://" in value:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.port:
            host += f":{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    # Do not echo unknown strings that may contain credentials.
    match = re.fullmatch(r"(?:[^@\s]+@)?([^:\s]+):([^\s]+)", value)
    return f"{match[1]}:{match[2]}" if match else "<nonstandard remote omitted>"


def matches_expected(value: str) -> bool:
    try:
        if "://" in value:
            parsed = urlsplit(value)
            if parsed.scheme not in {"https", "ssh"} or parsed.hostname != "github.com":
                return False
            if parsed.query or parsed.fragment or parsed.password:
                return False
            if parsed.scheme == "https" and parsed.username is not None:
                return False
            if parsed.scheme == "ssh" and parsed.username != "git":
                return False
            if parsed.port is not None and not (parsed.scheme == "https" and parsed.port == 443):
                return False
            path = parsed.path
        else:
            match = re.fullmatch(r"git@github\.com:(.+)", value)
            if not match:
                return False
            path = match[1]
        path = path.strip("/")
        if path.lower().endswith(".git"):
            path = path[:-4]
        return path.lower() == EXPECTED
    except (ValueError, TypeError):
        return False


def inspect(root: Path) -> int:
    if not shutil.which("git"):
        print("BLOCKED: git is not installed or not on PATH.")
        return 2
    if not root.is_dir():
        print("BLOCKED: target directory does not exist.")
        return 2

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(root), *args], text=True,
                              encoding="utf-8", errors="replace", capture_output=True,
                              timeout=15, check=False, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})

    try:
        top = git("rev-parse", "--show-toplevel")
        if top.returncode:
            print("NOT_A_REPOSITORY: no files or Git state were changed.")
            return 2
        if Path(top.stdout.strip()).resolve() != root.resolve():
            print("BLOCKED: target is inside a different repository, not its root.")
            return 2
        branch = git("branch", "--show-current").stdout.strip() or "<detached/unborn>"
        head = git("rev-parse", "--verify", "HEAD")
        status = git("status", "--short", "--branch")
        remote = git("remote", "get-url", "--all", "origin")
        urls = [u for u in remote.stdout.splitlines() if u.strip()]
        print("READ_ONLY: no network calls or modifications performed.")
        print(f"branch: {branch}")
        print(f"HEAD: {head.stdout.strip() if head.returncode == 0 else '<no commit>'}")
        print("worktree:\n" + status.stdout.rstrip())
        if not urls:
            print("ORIGIN_MISSING: inspect history before adding a remote.")
            return 3
        for value in urls:
            try:
                sanitized = sanitize_remote(value)
            except ValueError:
                sanitized = "<invalid remote omitted>"
            print(f"origin: {sanitized}")
        push = git("remote", "get-url", "--push", "--all", "origin")
        pushes = [u for u in push.stdout.splitlines() if u.strip()]
        good = bool(pushes) and all(matches_expected(u) for u in urls + pushes)
        print("REMOTE_MATCH" if good else "REMOTE_MISMATCH_OR_UNSAFE: do not push automatically.")
        print("Remote authentication, branch protection and collaborator permissions are NOT checked.")
        return 0 if good else 3
    except subprocess.TimeoutExpired:
        print("BLOCKED: local Git command timed out. No mutation was requested.")
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    return inspect(parser.parse_args().root)


if __name__ == "__main__":
    raise SystemExit(main())
