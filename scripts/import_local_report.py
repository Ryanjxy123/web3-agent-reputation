"""Operator-only PostgreSQL schema initialization and retained report import."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

import psycopg

from reputation_platform.db import Repository
from reputation_platform.settings import load_database_url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, nargs="?", help="本仓库 runtime 中的报告目录或 report.json")
    parser.add_argument("--initialize", action="store_true", help="创建首版 PostgreSQL 表和追加写保护")
    parser.add_argument("--candidates", type=Path, help="导入 runtime 中的候选准入报告，不赋分")
    args = parser.parse_args()
    if not (args.initialize or args.candidates or args.report):
        parser.error("至少指定 --initialize、--candidates 或一个报告目录")
    try:
        repository = Repository(load_database_url())
        if args.initialize:
            repository.initialize()
            print("schema: initialized")
        if args.candidates:
            print(f"candidates: {repository.import_candidates(args.candidates)}")
        if args.report:
            summary = repository.import_report(args.report)
            print(summary.model_dump_json(indent=2))
    except psycopg.Error:
        print("数据库操作失败；请检查本地 PostgreSQL 和私有连接配置。", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        print(f"导入未完成：{type(error).__name__}。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
