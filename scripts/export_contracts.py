"""Generate public JSON Schema and TypeScript contracts from core models."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "core" / "src"))

from reputation_core import (  # noqa: E402
    AdmissionReport, BehaviorVerification, BinaryPrediction, DeclarationAnalysis, DisclosureVerification,
    EvaluationReport, LiquidityHistoryDescriptor, LiquidityVerification, MarketSettlementVerification,
    PlanSelection, PredictionChainVerification, PredictionHistoryDescriptor, PredictionToolDescriptor,
    ProbeObservation, ScoredSample, ScoringOutcome, SourceDocument,
)
from reputation_core.application import (
    AgentDetail, AgentSummary, EvaluationJob, EvaluationSubmission, HealthStatus, ReportSummary,
)

MODELS = {"admission-report": AdmissionReport, "probe-observation": ProbeObservation,
          "source-document": SourceDocument, "declaration-analysis": DeclarationAnalysis,
          "liquidity-verification": LiquidityVerification, "disclosure-verification": DisclosureVerification,
          "behavior-verification": BehaviorVerification, "liquidity-history-descriptor": LiquidityHistoryDescriptor,
          "plan-selection": PlanSelection, "binary-prediction": BinaryPrediction, "scored-sample": ScoredSample,
          "prediction-chain-verification": PredictionChainVerification,
          "prediction-tool-descriptor": PredictionToolDescriptor,
          "prediction-history-descriptor": PredictionHistoryDescriptor,
          "market-settlement-verification": MarketSettlementVerification,
          "scoring-outcome": ScoringOutcome, "evaluation-report": EvaluationReport,
          "agent-summary": AgentSummary, "agent-detail": AgentDetail, "report-summary": ReportSummary,
          "evaluation-job": EvaluationJob, "evaluation-submission": EvaluationSubmission,
          "health-status": HealthStatus}
ANNOTATIONS = {"title", "description", "default", "format", "readOnly", "$defs", "$schema"}
SHAPES = {"$ref", "const", "enum", "anyOf", "type", "items", "properties", "required",
          "additionalProperties", "minLength", "minItems", "minimum", "maximum"}


def to_typescript(schema: dict, names: set[str]) -> str:
    unsupported = set(schema) - ANNOTATIONS - SHAPES
    if unsupported:
        raise ValueError(f"Unsupported schema keywords: {sorted(unsupported)}")
    for keyword, kind in (("minLength", "string"), ("minItems", "array")):
        if keyword in schema and (schema.get("type") != kind or schema[keyword] != 1):
            raise ValueError(f"Only {keyword}=1 on {kind} is supported")
    if "$ref" in schema:
        prefix = "#/$defs/"
        reference = schema["$ref"]
        if not reference.startswith(prefix) or reference[len(prefix):] not in names:
            raise ValueError(f"Unsupported reference: {reference}")
        return reference[len(prefix):]
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        return " | ".join(json.dumps(value, ensure_ascii=False) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(to_typescript(option, names) for option in schema["anyOf"])
    kind = schema.get("type")
    if isinstance(kind, list):
        return " | ".join(to_typescript({"type": item}, names) for item in kind)
    if kind == "array":
        item = to_typescript(schema["items"], names)
        return f"[{item}, ...Array<{item}>]" if "minItems" in schema else f"Array<{item}>"
    if kind == "object":
        if schema.get("additionalProperties", False) is not False:
            raise ValueError("Open object schemas are not supported")
        required = set(schema.get("required", []))
        fields = []
        for name, value in schema.get("properties", {}).items():
            modifier = "readonly " if value.get("readOnly") else ""
            optional = "" if name in required else "?"
            fields.append(f"  {modifier}{json.dumps(name)}{optional}: {to_typescript(value, names)};")
        return "{\n" + "\n".join(fields) + "\n}"
    primitives = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}
    if kind == "string" and "minLength" in schema:
        return "/** @minLength 1; validated by JSON Schema/Pydantic */ string"
    if kind in primitives:
        if kind in ("number", "integer") and ("minimum" in schema or "maximum" in schema):
            limits = " ".join(f"@{key} {schema[key]}" for key in ("minimum", "maximum") if key in schema)
            return f"/** {limits}; validated by JSON Schema/Pydantic */ number"
        return primitives[kind]
    raise ValueError(f"Unsupported schema shape: {schema}")


def main() -> None:
    schemas = {name: model.model_json_schema(mode="serialization") for name, model in MODELS.items()}
    definitions = {}
    for schema in schemas.values():
        for name, definition in schema.get("$defs", {}).items():
            if name in definitions and definitions[name] != definition:
                raise ValueError(f"Conflicting shared definition: {name}")
            definitions[name] = definition
    for name, model in MODELS.items():
        definition = {key: value for key, value in schemas[name].items() if key != "$defs"}
        if model.__name__ in definitions and definitions[model.__name__] != definition:
            raise ValueError(f"Conflicting root definition: {model.__name__}")
        definitions[model.__name__] = definition
    names = set(definitions)
    declarations = [f"export type {name} = {to_typescript(definition, names)};" for name, definition in definitions.items()]
    output = ROOT / "packages" / "core" / "generated"
    output.mkdir(parents=True, exist_ok=True)
    for name, schema in schemas.items():
        document = {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}
        (output / f"{name}.schema.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "contracts.ts").write_text("// Generated by scripts/export_contracts.py; do not edit.\n\n" + "\n\n".join(declarations) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
