"""Compose preparation preserves real host deployment bytes and isolates service secrets."""

import json
import os
import shutil

import pytest
from fastapi.testclient import TestClient
from fixture_agents.service import create_app
from reputation_platform.application.local_deploy import deploy
from reputation_platform.application.local_seed import seed

from scripts.prepare_compose_runtime import CONTAINER_RPC, prepare
from tests.integration.test_fixture_agents import ROOT, anvil_node, task

pytestmark = pytest.mark.chain


@pytest.fixture(scope="module")
def compose_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("compose")
    shutil.copytree(ROOT / "contracts/abi", root / "contracts/abi")
    source = root / "runtime/host"
    with anvil_node() as (url, _):
        deployment = deploy(ROOT, url, source)
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("FIXTURE_HOST_A", "fixture-a")
            patch.setenv("FIXTURE_HOST_D", "fixture-d")
            patch.setenv("FIXTURE_PORT_A", "9101")
            patch.setenv("FIXTURE_PORT_D", "9102")
            seed(ROOT, deployment, source)
        yield root, source, deployment


def test_only_four_configs_copied_with_container_rpc_and_host_unchanged(compose_source, tmp_path):
    root, source, deployment = compose_source
    original = {path.name: path.read_bytes() for path in source.iterdir()}
    output = root / "runtime" / tmp_path.name
    prepare(root, source, output)
    assert {path.name for path in output.iterdir()} == {
        "deployment.json", "publisher-secret.json", "fixture-a.json", "fixture-d.json",
    }
    assert {path.name: path.read_bytes() for path in source.iterdir()} == original
    container = json.loads((output / "deployment.json").read_bytes())
    assert container == {**deployment.model_dump(mode="json"), "rpc_url": CONTAINER_RPC}
    for sample in ("a", "d"):
        before = json.loads(original[f"fixture-{sample}.json"])
        after = json.loads((output / f"fixture-{sample}.json").read_bytes())
        assert after == {**before, "deployment": container}
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o700
        assert all(path.stat().st_mode & 0o777 == 0o444 for path in output.iterdir())


def test_existing_output_and_outside_or_nested_paths_are_rejected(compose_source, tmp_path):
    root, source, _ = compose_source
    output = root / "runtime" / tmp_path.name
    output.mkdir()
    marker = output / "ledger.sqlite3"
    marker.write_bytes(b"must preserve")
    with pytest.raises(FileExistsError):
        prepare(root, source, output)
    assert marker.read_bytes() == b"must preserve"
    for invalid in (tmp_path / "outside", source / "nested", root / "runtime"):
        with pytest.raises(ValueError, match="separate directories"):
            prepare(root, source, invalid)


@pytest.mark.parametrize("fault", ["hosts", "publisher", "deployment", "endpoint"])
def test_inconsistent_seed_or_service_configs_are_rejected_before_output(
    compose_source, tmp_path, fault,
):
    root, original, _ = compose_source
    source = root / "runtime" / ("source-" + tmp_path.name)
    shutil.copytree(original, source)
    name = {
        "hosts": "seed-intent.json", "publisher": "publisher-secret.json",
        "deployment": "fixture-a.json", "endpoint": "fixture-a.json",
    }[fault]
    path = source / name
    value = json.loads(path.read_bytes())
    if fault == "hosts":
        value["hosts"] = ["127.0.0.1", "127.0.0.1"]
    elif fault == "publisher":
        value["private_key"] = json.loads((source / "setup-secrets.json").read_bytes())["keys"]["admin"]
    elif fault == "deployment":
        value["deployment"]["rpc_url"] = "http://127.0.0.1:8545"
    else:
        value["metadata"]["endpoints"][0]["host"] = "127.0.0.1"
    path.write_text(json.dumps(value), encoding="utf-8")
    output = root / "runtime" / ("output-" + tmp_path.name)
    with pytest.raises(ValueError):
        prepare(root, source, output)
    assert not output.exists()


def test_fixture_ledger_override_works_without_writing_beside_config(compose_source, tmp_path, monkeypatch):
    _, source, deployment = compose_source
    config = tmp_path / "readonly-config.json"
    config.write_bytes((source / "fixture-a.json").read_bytes())
    ledger = tmp_path / "volume/tasks.sqlite3"
    monkeypatch.setenv("FIXTURE_LEDGER_PATH", str(ledger))
    envelope = task(deployment)
    with TestClient(create_app(config, run_worker=False)) as client:
        response = client.post(
            "/tasks", json=envelope.model_dump(mode="json"),
            headers={"Idempotency-Key": envelope.request_id},
        )
        assert response.status_code == 202
    with TestClient(create_app(config, run_worker=False)) as restarted:
        assert restarted.get(f"/tasks/{envelope.request_id}").json() == response.json()
    assert ledger.is_file()
    assert not config.with_suffix(".sqlite3").exists()
