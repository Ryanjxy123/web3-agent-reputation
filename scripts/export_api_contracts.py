"""Export the actual FastAPI schema without opening a database or reading secrets."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_platform.api import create_app
from reputation_platform.db import Repository


def main() -> None:
    # Construct routes only; repository operations are never invoked for schema export.
    app = create_app(Repository("dbname=contract_generation", root=ROOT))
    output = ROOT / "services/platform/generated"
    output.mkdir(exist_ok=True)
    (output / "openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
