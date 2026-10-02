"""Generate JSON Schema and initial OpenAPI components from core DTOs."""
import argparse
import json
from pathlib import Path

from pydantic import BaseModel
from reputation_core import models

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "packages/schemas/generated"


def render() -> dict[str, str]:
    definitions = {}
    documents = {}
    seen = set()
    for name in models.__all__:
        model = getattr(models, name)
        if not isinstance(model, type) or not issubclass(model, BaseModel) or model in seen:
            continue
        seen.add(model)
        schema = model.model_json_schema()
        documents[f"{model.__name__}.schema.json"] = json.dumps(
            schema, ensure_ascii=False, sort_keys=True, indent=2
        ) + "\n"
        openapi_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        definitions.update(openapi_schema.pop("$defs", {}))
        definitions[model.__name__] = openapi_schema
    # M0-03 publishes components only. Actual routes are exported from FastAPI at M0-05.
    documents["openapi.json"] = json.dumps({
        "openapi": "3.1.0",
        "info": {"title": "Web3 Agent Reputation", "version": "1.0.0"},
        "paths": {},
        "components": {"schemas": definitions},
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return documents


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    documents = render()
    if args.check:
        drift = [
            name for name, text in documents.items()
            if not (OUTPUT / name).is_file() or (OUTPUT / name).read_text(encoding="utf-8") != text
        ]
        if drift:
            print("SCHEMA_DRIFT: " + ", ".join(drift))
            return 1
    else:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for name, text in documents.items():
            (OUTPUT / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(documents)} generated schema documents verified" if args.check else f"Generated {len(documents)} schema documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
