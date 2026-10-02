"""Real HTTP/Anvil protocol smoke. Synthetic snapshot, not a platform evaluation."""

import argparse
import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta

from reputation_core.models import ControlledTaskView, LocalDeployment, TaskEnvelope
from reputation_platform.application.local_deploy import contract_abi, local_web3, write_json
from reputation_platform.infrastructure.db.connection import repo_root
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient
from web3 import Web3


async def main(recheck: bool = False) -> None:
    root = repo_root()
    runtime = root / "runtime/local-chain"
    deployment = LocalDeployment.model_validate_json((runtime / "deployment.json").read_bytes())
    samples = json.loads((runtime / "samples.json").read_bytes())
    web3 = local_web3(deployment.rpc_url)
    record = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.record.address),
        abi=contract_abi(root, "DemoRecordRegistry"),
    )
    http = SafeHttpClient(frozenset({"http://127.0.0.1:9101", "http://127.0.0.1:9102"}))
    results = []
    previous = (
        json.loads((runtime / "protocol-smoke.json").read_bytes())["results"] if recheck else []
    )
    try:
        for sample, port in (("a", 9101), ("d", 9102)):
            task = TaskEnvelope(
                request_id="0x" + secrets.token_hex(32),
                record_hash="0x" + secrets.token_hex(32),
                snapshot_hash="0x" + secrets.token_hex(32),
                chain_id="31337",
                chain_instance_id=deployment.chain.instance_hash,
                target_contract=deployment.record.address,
                deadline=(datetime.now(UTC) + timedelta(seconds=60))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
            )
            prior = next((item for item in previous if item["sample"] == sample.upper()), None)
            if prior:
                task = TaskEnvelope.model_validate(prior["task"])
            origin = f"http://127.0.0.1:{port}"
            response = await http.request(
                "POST",
                origin,
                "/tasks",
                json=task.model_dump(mode="json"),
                request_id=task.request_id,
            )
            assert response.status == 202
            async with asyncio.timeout(65):
                while True:
                    response = await http.request("GET", origin, "/tasks/" + task.request_id)
                    state = ControlledTaskView.model_validate_json(response.body)
                    if state.task_status in {"succeeded", "failed"}:
                        break
                    await asyncio.sleep(0.5)
            assert state.task_status == "succeeded" and state.result
            if prior:
                assert state.result.tx_hash == prior["tx_hash"]
            receipt = web3.eth.get_transaction_receipt(state.result.tx_hash)
            event = record.events.RecordAnchored().process_receipt(receipt)[0]["args"]
            request_match = "0x" + bytes(event["requestId"]).hex() == task.request_id
            hash_match = "0x" + bytes(event["recordHash"]).hex() == task.record_hash
            assert receipt["status"] == 1
            assert event["executor"].lower() == samples[sample]["executor"]
            assert (request_match and hash_match) == (sample == "a")
            matching_logs = record.events.RecordAnchored().get_logs(
                from_block=0,
                argument_filters={
                    "executor": Web3.to_checksum_address(samples[sample]["executor"]),
                    "requestId": task.request_id,
                },
            )
            assert len(matching_logs) == (1 if sample == "a" else 0)
            results.append(
                {
                    "sample": sample.upper(),
                    "task": task.model_dump(mode="json"),
                    "tx_hash": state.result.tx_hash,
                    "receipt_status": receipt["status"],
                    "event_request_id": "0x" + bytes(event["requestId"]).hex(),
                    "event_record_hash": "0x" + bytes(event["recordHash"]).hex(),
                    "request_match": request_match,
                    "hash_match": hash_match,
                }
            )
        write_json(
            runtime / "protocol-smoke.json",
            {"scope": "controlled_protocol_only_synthetic_snapshot", "results": results},
        )
        print(
            "PROTOCOL_SMOKE_PASS: real A match and D unrelated successful transaction; platform evaluation still separate"
        )
    finally:
        await http.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recheck", action="store_true", help="Repeat the saved requests after service restart"
    )
    asyncio.run(main(parser.parse_args().recheck))
