"""Configuration errors fail before any RPC call or key is read."""

import json

import pytest
from fixture_agents.service import Agent

from tests.factories import ADDRESS, HASH, slot


@pytest.mark.parametrize(
    ("updates", "error"),
    [
        ({"mode": "unknown"}, "UNSUPPORTED_FIXTURE_MODE"),
        ({"fault_seed": ""}, "INVALID_FAULT_SEED"),
        ({"fault_seed": 3}, "INVALID_FAULT_SEED"),
        ({"fault_seed": "x" * 129}, "INVALID_FAULT_SEED"),
        ({"failure_every": True}, "INVALID_FAILURE_EVERY"),
        ({"failure_every": 0}, "INVALID_FAILURE_EVERY"),
        ({"failure_every": 1001}, "INVALID_FAILURE_EVERY"),
        ({"failure_every": 2.5}, "INVALID_FAILURE_EVERY"),
        ({"delay_seconds": True}, "INVALID_DELAY_SECONDS"),
        ({"delay_seconds": 0}, "INVALID_DELAY_SECONDS"),
        ({"delay_seconds": 66}, "INVALID_DELAY_SECONDS"),
        ({"delay_seconds": "20"}, "INVALID_DELAY_SECONDS"),
    ],
)
def test_invalid_fault_config_is_rejected_without_external_effects(tmp_path, updates, error):
    contract = {
        "address": ADDRESS,
        "code_hash": HASH,
        "transaction_hash": HASH,
        "block_number": "1",
        "block_hash": HASH,
    }
    value = {
        "deployment": {
            "rpc_url": "http://127.0.0.1:18545",
            "chain": slot().expected.execution_chain.model_dump(mode="json"),
            "registry": contract,
            "record": contract,
            "anchor": contract,
            "admin": ADDRESS,
            "evaluator": ADDRESS,
            "platform_instance_id": HASH,
        },
        "metadata": {},
        "mode": "normal",
        **updates,
    }
    config = tmp_path / "fixture.json"
    config.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        Agent(config)
    assert not config.with_suffix(".sqlite3").exists()
