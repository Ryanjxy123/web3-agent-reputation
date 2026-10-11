"""Copy a verified, explicitly seeded host runtime into a new Compose config directory."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from eth_account import Account
from reputation_core.models import LocalDeployment
from reputation_platform.application.local_deploy import local_web3, verify_deployment

ROOT = Path(__file__).resolve().parents[1]
CONTAINER_RPC = "http://anvil:8545"


def prepare(root: Path, source: Path, output: Path) -> None:
    runtime = (root / "runtime").resolve()
    source, output = source.resolve(), output.resolve()
    if (
        not source.is_relative_to(runtime) or not output.is_relative_to(runtime)
        or source == runtime or output == runtime
        or output.is_relative_to(source) or source.is_relative_to(output)
    ):
        raise ValueError("Source and output must be separate directories inside repository runtime")
    if output.exists():
        raise FileExistsError("Compose output must be new; preserve existing configs and ledgers")
    deployment = LocalDeployment.model_validate_json((source / "deployment.json").read_bytes())
    if urlsplit(deployment.rpc_url).hostname != "127.0.0.1":
        raise ValueError("Source must be the explicit host deployment with a loopback RPC")
    verify_deployment(local_web3(deployment.rpc_url), deployment, root)
    intent = json.loads((source / "seed-intent.json").read_bytes())
    if (
        intent["chain_instance"] != deployment.chain.instance_hash
        or intent["hosts"] != ["fixture-a", "fixture-d"]
        or intent.get("ports", [9101, 9102]) != [9101, 9102]
    ):
        raise ValueError("Source must be seeded for Compose fixture-a/d hosts and ports")
    publisher = json.loads((source / "publisher-secret.json").read_bytes())
    if Account.from_key(publisher["private_key"]).address.lower() != deployment.evaluator:
        raise ValueError("Publisher key does not match the verified deployment")
    container = deployment.model_copy(update={"rpc_url": CONTAINER_RPC}).model_dump(mode="json")
    documents = {
        "deployment.json": container,
        "publisher-secret.json": {"private_key": publisher["private_key"]},
    }
    samples = json.loads((source / "samples.json").read_bytes())
    for sample, port in (("a", 9101), ("d", 9102)):
        fixture = json.loads((source / f"fixture-{sample}.json").read_bytes())
        if LocalDeployment.model_validate(fixture["deployment"]) != deployment:
            raise ValueError("Fixture deployment does not match the verified host deployment")
        if (
            fixture["metadata"] != samples[sample]["metadata"]
            or fixture["mode"] != ("normal" if sample == "a" else "replay")
            or fixture["metadata"]["declared_executor"]
            != Account.from_key(fixture["private_key"]).address.lower()
            or fixture["metadata"]["endpoints"] != [{
                "endpoint_id": f"fixture-{sample}", "scheme": "http",
                "host": f"fixture-{sample}", "port": port, "path": "/tasks",
                "method": "POST", "protocol": "controlled-http-v1",
            }]
        ):
            raise ValueError("Fixture must retain the seeded A/D identity and endpoint")
        fixture["deployment"] = container
        documents[f"fixture-{sample}.json"] = fixture
    # Individual read-only file mounts let UID 10001 read; host parent stays owner-only.
    output.mkdir(mode=0o700, parents=True)
    for name, value in documents.items():
        path = output / name
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        os.chmod(path, 0o444)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="existing deploy/seed host runtime")
    parser.add_argument("--output", type=Path, default=Path("runtime/compose-chain"))
    args = parser.parse_args()
    prepare(ROOT, ROOT / args.source, ROOT / args.output)
    print("COMPOSE_RUNTIME_PREPARED: verified chain; four whitelisted configs; source unchanged")


if __name__ == "__main__":
    main()
