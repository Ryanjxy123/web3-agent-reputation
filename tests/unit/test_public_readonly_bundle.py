from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from reputation_core.evidence import canonical_bytes, hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AnchorReceipt,
    EvidenceManifest,
    EvidenceRecord,
    ManifestDocument,
    PublicationContext,
)
from reputation_core.models.public_evaluation import PublicReadonlyRunPlan
from reputation_core.public_reporting import build_public_readonly_report
from reputation_core.public_verifier import public_observation, verify_public_readonly
from reputation_platform.application.errors import ApplicationError
from reputation_platform.application.public_reports import refresh_public_inputs
from reputation_verifier import VerificationError, verify_bundle

from tests.factories import ADDRESS, ZERO, slot
from tests.unit.test_public_evaluation_core import make_input
from tests.unit.test_verifier import rewrite_bundle


def after(value):
    return (datetime.fromisoformat(value.replace("Z", "+00:00")) + timedelta(seconds=1)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def make_public_bundle(tmp_path, *, protocol="akashi-http-readonly-v1", no_business=False):
    data = make_input(protocol=protocol)
    if no_business:
        omitted = set(data.business_evidence_refs)
        data = data.model_copy(update={
            "business_evidence_refs": (),
            "packets": tuple(packet for packet in data.packets if packet.record.evidence_id not in omitted),
        })
    frozen = data.model_copy(update={"observed_at": after(data.observed_at)})
    policy = strict_json((Path(__file__).resolve().parents[2] / "configs/policies/policy-v1.json").read_bytes())
    plan = PublicReadonlyRunPlan(
        run_id=uuid4(), snapshot_hash=data.snapshot.snapshot_hash,
        review_version=data.review_version, policy_hash=hash_json(policy),
        planning_time=data.slot.expected.window_start, slots=(data.slot,),
    )
    files, records = {}, {}

    def add(body, source, observed_at=data.observed_at):
        raw = canonical_bytes(body)
        digest = hash_bytes(raw)
        record = EvidenceRecord(
            evidence_id=uuid4(), path=f"blobs/{digest[2:]}.bin", blob_hash=digest,
            byte_count=len(raw), media_type="application/json", source=source,
            observed_at=observed_at, collector_version="bundle-test-v1",
            redaction_profile="credentials-v1", trust_group="frozen-report",
        )
        files[record.path] = raw
        records[record.evidence_id] = record
        return record

    for packet in data.packets:
        files[packet.record.path] = canonical_bytes(packet.body)
        records[packet.record.evidence_id] = packet.record
    original_record = add(data.model_dump(mode="json"), "public-readonly-verification-input")
    freeze_record = add(frozen.model_dump(mode="json"), "report-freeze-public-readonly-input",
                        frozen.observed_at)
    result = verify_public_readonly(data, (original_record.evidence_id,))
    observation = public_observation(data)
    documents = {
        "policy.json": policy,
        "snapshot_core.json": data.snapshot.core.model_dump(mode="json"),
        "public_snapshot.json": data.snapshot.model_dump(mode="json"),
        "claims_review.json": data.review.model_dump(mode="json"),
        "readonly_associations.json": [data.association.model_dump(mode="json")],
        "access_grants.json": [data.grant.model_dump(mode="json")] if data.grant else [],
        "bindings.json": [], "run_plan.json": plan.model_dump(mode="json"),
        "observations.json": [observation.model_dump(mode="json")],
        "assertions.json": [item.model_dump(mode="json") for item in sorted(
            result.assertions, key=lambda item: str(item.assertion_id))],
        "verification.json": {
            "schema_version": "public-readonly-replay-v1", "tasks": [{
                "slot_id": str(data.slot.slot_id),
                "input_evidence_id": str(original_record.evidence_id),
                "freeze_evidence_id": str(freeze_record.evidence_id),
            }],
        },
    }
    aliases = []
    for path, body in sorted(documents.items()):
        record = add(body, f"report-document:{path}", frozen.observed_at)
        aliases.append(ManifestDocument(path=path, evidence_id=record.evidence_id))
        files[path] = files[record.path]
    publication = PublicationContext(
        chain=slot().expected.execution_chain, contract=ADDRESS, publisher=ADDRESS,
        confirmation_depth=1, previous_report_hash=ZERO, head_sequence=0,
        head_block_number="1", head_block_hash=ZERO, platform_instance_id=data.platform_instance_id,
    )
    manifest = EvidenceManifest(
        publication=publication, documents=tuple(aliases),
        evidence=tuple(sorted(records.values(), key=lambda item: str(item.evidence_id))),
    )
    report = build_public_readonly_report(
        plan, (data,), (original_record.evidence_id,), (observation,), policy,
        evaluated_at=after(frozen.observed_at), code_version="0" * 40,
        manifest_hash=hash_json(manifest.model_dump(mode="json")), previous_report_hash=ZERO,
    )
    receipt = AnchorReceipt(
        report_hash=hash_json(report.model_dump(mode="json")), status="NOT_REQUESTED",
        trusted_chain_key="local-demo", chain_instance_id=publication.chain.instance_hash,
        contract=ADDRESS, publisher=ADDRESS, tx_hash=None, sequence=None,
        block_number=None, block_hash=None, confirmations=0,
    )
    files.update({
        "report_core.json": canonical_bytes(report.model_dump(mode="json")),
        "evidence_manifest.json": canonical_bytes(manifest.model_dump(mode="json")),
        "anchor_receipt.json": canonical_bytes(receipt.model_dump(mode="json")),
    })
    path = tmp_path / "public.zip"
    with ZipFile(path, "w") as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)
    return path, original_record.evidence_id, freeze_record.evidence_id, data


@pytest.mark.parametrize("protocol", ["akashi-http-readonly-v1", "akashi-mcp-readonly-v1"])
def test_public_bundle_replays_originals_scores_and_unrequested_local_anchor(tmp_path, protocol):
    path, _, _, data = make_public_bundle(tmp_path, protocol=protocol)
    result = verify_bundle(str(path))
    assert result["offline"] == "PASS" and result["task_counts"]["PASS"] == 1
    assert result["assessment_comparison"] == "MATCH"
    assert result["publication"] == "LOCAL_ANVIL" and result["publication_status"] == "UNANCHORED"
    assert result["anchor"]["status"] == "NOT_CHECKED"
    assert result["task_results"][0]["live_chain"]["status"] == "NOT_CHECKED"
    assert data.association.executor_outcome == "UNKNOWN"
    with ZipFile(path) as archive:
        report = strict_json(archive.read("report_core.json"))
    assert report["schema_version"] == "1.6.0"
    assert report["scores"]["evaluation_state"] == "PARTIAL"
    assert report["scores"]["overall_score_bp"] is None


def test_public_bundle_missing_business_originals_remains_unknown(tmp_path):
    path, _, _, _ = make_public_bundle(tmp_path, no_business=True)
    result = verify_bundle(str(path))
    assert result["offline"] == "PASS" and result["task_counts"]["UNKNOWN"] == 1


@pytest.mark.parametrize("field", ["raw_statistics", "scores", "task_results", "evidence_sufficiency"])
def test_public_report_semantic_changes_fail_after_rehash(tmp_path, field):
    path, _, _, _ = make_public_bundle(tmp_path)

    def change(core):
        if field == "raw_statistics":
            core[field]["availability"]["responded"] = 999
        elif field == "scores":
            core[field]["limitations"] = ["forged limitation"]
        elif field == "task_results":
            core[field][0].update(outcome="FAIL", reason_code="SEMANTIC_MISMATCH")
        else:
            core[field]["missing_evidence"] = ["forged missing source"]

    changed = tmp_path / "changed.zip"
    rewrite_bundle(path, changed, core_change=change)
    with pytest.raises(VerificationError):
        verify_bundle(str(changed))


@pytest.mark.parametrize("document", [
    "observations.json", "access_grants.json", "claims_review.json", "readonly_associations.json",
    "public_snapshot.json", "verification.json", "run_plan.json",
])
def test_public_documents_cannot_diverge_after_rehash(tmp_path, document):
    path, _, _, _ = make_public_bundle(tmp_path)

    def change(body):
        if document == "observations.json":
            body[0]["latency_ms"] += 1
        elif document == "access_grants.json":
            body[0]["max_tasks"] = 1 if body[0]["max_tasks"] != 1 else 2
        elif document == "claims_review.json":
            body["review_version"] += 1
        elif document == "readonly_associations.json":
            body[0]["target_url"] = "https://attacker.invalid/proof"
        elif document == "public_snapshot.json":
            body["snapshot_id"] = str(uuid4())
        elif document == "verification.json":
            body["tasks"].append(body["tasks"][0])
        else:
            body["slots"][0]["task"]["query"] = {"hash": "a" * 64}

    changed = tmp_path / "changed-doc.zip"
    rewrite_bundle(path, changed, document_change={document: change})
    with pytest.raises(VerificationError):
        verify_bundle(str(changed))


@pytest.mark.parametrize("field", ["dispatch_payload_hash", "association", "packets", "agent_evidence_refs"])
def test_public_input_semantic_tampering_fails_after_rehash(tmp_path, field):
    path, original_id, frozen_id, _ = make_public_bundle(tmp_path)

    def change(body):
        if field == "dispatch_payload_hash":
            body[field] = ZERO
        elif field == "association":
            body[field]["target_url"] = "https://attacker.invalid/proof"
        elif field == "packets":
            body[field][0]["record"]["trust_group"] = "forged-source"
        else:
            body[field] = body[field][:-1]

    changed = tmp_path / "changed-input.zip"
    rewrite_bundle(path, changed, evidence_change={original_id: change, frozen_id: change})
    with pytest.raises(VerificationError):
        verify_bundle(str(changed))


def test_public_frozen_input_cannot_change_original_context(tmp_path):
    path, _, frozen_id, _ = make_public_bundle(tmp_path)
    changed = tmp_path / "changed-freeze.zip"
    rewrite_bundle(path, changed, evidence_change={
        frozen_id: lambda body: body.update(platform_instance_id=ZERO),
    })
    with pytest.raises(VerificationError):
        verify_bundle(str(changed))


def test_public_publication_platform_cannot_diverge_from_input_after_rehash(tmp_path):
    path, _, _, _ = make_public_bundle(tmp_path)
    changed = tmp_path / "changed-platform.zip"
    rewrite_bundle(path, changed, manifest_change=lambda manifest: manifest["publication"].update(
        platform_instance_id="0x" + "ef" * 32,
    ))
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("schema", ["1.0.0", "1.5.0"])
def test_public_suite_cannot_use_old_report_versions(tmp_path, schema):
    path, _, _, _ = make_public_bundle(tmp_path)
    changed = tmp_path / "changed-schema.zip"
    rewrite_bundle(path, changed, core_change=lambda body: body.update(schema_version=schema))
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "RULE_VERSION_MISMATCH"


def rewrite_public_originals(path, destination, changes):
    """Recommit CAS, nested packets, aliases, manifest and receipt; keep reported judgement."""
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = strict_json(files["evidence_manifest.json"])
    by_id = {record["evidence_id"]: record for record in manifest["evidence"]}

    def update(record, body):
        raw = canonical_bytes(body)
        digest = hash_bytes(raw)
        record.update(path=f"blobs/{digest[2:]}.bin", blob_hash=digest, byte_count=len(raw))
        files[record["path"]] = raw

    changed_bodies = {}
    for identifier, change in changes.items():
        record = by_id[str(identifier)]
        body = strict_json(files[record["path"]])
        change(body)
        update(record, body)
        changed_bodies[str(identifier)] = body
    for record in manifest["evidence"]:
        if record["source"] not in {
            "public-readonly-verification-input", "report-freeze-public-readonly-input"
        }:
            continue
        body = strict_json(files[record["path"]])
        for packet in body["packets"]:
            identifier = packet["record"]["evidence_id"]
            if identifier in changed_bodies:
                packet.update(record=by_id[identifier], body=changed_bodies[identifier])
        update(record, body)
    paths = {record["path"] for record in manifest["evidence"]}
    files = {name: raw for name, raw in files.items() if not name.startswith("blobs/") or name in paths}
    for document in manifest["documents"]:
        files[document["path"]] = files[by_id[document["evidence_id"]]["path"]]
    core = strict_json(files["report_core.json"])
    core["evidence_manifest_hash"] = hash_json(manifest)
    receipt = strict_json(files["anchor_receipt.json"])
    receipt["report_hash"] = hash_json(core)
    files.update({"report_core.json": canonical_bytes(core),
                  "evidence_manifest.json": canonical_bytes(manifest),
                  "anchor_receipt.json": canonical_bytes(receipt)})
    with ZipFile(destination, "w") as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)


@pytest.mark.parametrize("kind", ["metadata_cache", "proof_cache", "receipt_status", "query_wire"])
def test_public_original_semantics_are_replayed_after_every_commitment_is_recomputed(tmp_path, kind):
    path, _, _, data = make_public_bundle(tmp_path)
    packets = {packet.record.evidence_id: packet for packet in data.packets}
    if kind == "metadata_cache":
        identifier = next(ref for ref in data.identity_evidence_refs
                          if isinstance(packets[ref].body, dict)
                          and packets[ref].body.get("path") == "/.well-known/agent-registration.json"
                          and packets[ref].record.source == "public-readonly-response")
        changes = {identifier: lambda body: body["response"]["json"].update(name="forged cache")}
    elif kind == "proof_cache":
        identifier = data.agent_evidence_refs[1]
        changes = {identifier: lambda body: body["response"]["json"].update(anchored=False)}
    elif kind == "receipt_status":
        identifier = next(ref for ref in data.business_evidence_refs
                          if packets[ref].record.source == "public-readonly-response"
                          and packets[ref].body["request_json"]["method"] == "eth_getTransactionReceipt")

        def reverted_receipt(body):
            response = body["response"]
            response["json"]["result"]["status"] = "0x0"
            raw = canonical_bytes(response["json"])
            response.update(raw_body_utf8=raw.decode(), body_bytes=len(raw),
                            body_sha256=sha256(raw).hexdigest())

        changes = {identifier: reverted_receipt}
    else:
        changes = {identifier: lambda body: body.update(path="/proof?hash=" + "a" * 64)
                   for identifier in data.agent_evidence_refs[:2]}
    changed = tmp_path / "changed-original.zip"
    rewrite_public_originals(path, changed, changes)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "REPLAY_MISMATCH"


async def test_public_report_requires_a_lease_before_refreshing_any_source():
    with pytest.raises(ApplicationError, match="worker lease"):
        await refresh_public_inputs(SimpleNamespace(), (), (), (), None, None)


async def test_public_report_checks_original_cas_before_new_rpc(monkeypatch):
    data = make_input()
    identifier = uuid4()
    from reputation_platform.application.public_verification import (
        PublicReadonlyVerificationService,
    )

    async def no_rpc(*args, **kwargs):
        pytest.fail("Changed original CAS reached public RPC refresh")

    monkeypatch.setattr(PublicReadonlyVerificationService, "fresh_input", no_rpc)
    service = SimpleNamespace(db=None, identity=None, client_factory=None,
                              read_evidence=lambda _: b"{}")
    with pytest.raises(ApplicationError, match="differs from CAS"):
        await refresh_public_inputs(service, (data,), (verify_public_readonly(data, (identifier,)),),
                                    (identifier,), SimpleNamespace(), SimpleNamespace())


async def test_public_historical_rpc_unknown_freezes_without_upgrade_or_another_request(monkeypatch):
    data = make_input()
    omitted = set(data.business_evidence_refs)
    original = data.model_copy(update={
        "business_evidence_refs": (),
        "packets": tuple(packet for packet in data.packets if packet.record.evidence_id not in omitted),
    })
    identifier = uuid4()
    result = verify_public_readonly(original, (identifier,))
    assert result.outcome == "UNKNOWN" and result.reason_code == "PLATFORM_RPC_ERROR"
    from reputation_platform.application.public_verification import (
        PublicReadonlyVerificationService,
    )

    async def no_refresh(*args, **kwargs):
        pytest.fail("Historical UNKNOWN must retain its original evidence gap")

    monkeypatch.setattr(PublicReadonlyVerificationService, "fresh_input", no_refresh)
    packets = {packet.record.evidence_id: packet for packet in original.packets}
    service = SimpleNamespace(db=None, identity=None, client_factory=None,
                              read_evidence=lambda record: canonical_bytes(packets[record.evidence_id].body))
    refreshed = await refresh_public_inputs(service, (original,), (result,), (identifier,),
                                            SimpleNamespace(), SimpleNamespace())
    assert refreshed[0].packets == original.packets
    assert refreshed[0].business_evidence_refs == original.business_evidence_refs
    assert verify_public_readonly(refreshed[0], (identifier,)) == result
