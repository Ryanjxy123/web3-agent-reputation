"""Export only actual Foundry-generated ABI; --check rejects drift."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "contracts"
CONTRACTS = ("DemoAgentRegistry", "DemoRecordRegistry", "EvaluationAnchor")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    (ROOT / "abi").mkdir(exist_ok=True)
    for name in CONTRACTS:
        compiled = ROOT / "out" / f"{name}.sol" / f"{name}.json"
        abi = json.loads(compiled.read_text(encoding="utf-8"))["abi"]
        rendered = json.dumps(abi, sort_keys=True, indent=2) + "\n"
        target = ROOT / "abi" / f"{name}.json"
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != rendered:
                print(f"ABI_DRIFT: {name}")
                return 1
        else:
            target.write_text(rendered, encoding="utf-8", newline="\n")
    print("Three compiled ABIs verified" if args.check else "Three compiled ABIs exported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
