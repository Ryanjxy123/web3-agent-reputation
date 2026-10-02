from uuid import uuid4

from reputation_core.models import AgentRef, CaseSlot, ChainIdentity, ExpectedFacts, TaskEnvelope

HASH = "0x" + "a1" * 32
ZERO = "0x" + "00" * 32
ADDRESS = "0x" + "ab" * 20
NOW = "2026-10-02T12:00:00.000Z"
DEADLINE = "2026-10-02T12:01:00.000Z"


def agent():
    return AgentRef(chain_id="31337", registry_address=ADDRESS, agent_id=str(2**255 + 123))


def slot():
    chain = ChainIdentity(
        chain_id="31337",
        genesis_hash=HASH,
        deployment_instance_id=HASH,
        registry_code_hash=HASH,
        instance_hash=HASH,
    )
    expected = ExpectedFacts(
        agent_ref=agent(),
        snapshot_hash=HASH,
        execution_chain=chain,
        executor=ADDRESS,
        target_contract=ADDRESS,
        request_id=HASH,
        record_hash=HASH,
        binding_id=uuid4(),
        window_start=NOW,
        deadline=DEADLINE,
        pre_dispatch_block="1",
        pre_dispatch_block_hash=HASH,
        confirmation_depth=1,
    )
    task = TaskEnvelope(
        request_id=HASH,
        snapshot_hash=HASH,
        chain_id="31337",
        chain_instance_id=HASH,
        target_contract=ADDRESS,
        record_hash=HASH,
        deadline=DEADLINE,
    )
    return CaseSlot(
        slot_id=uuid4(),
        slot_key="anchor-1",
        capability_id="anchor_record",
        purpose="functional",
        case_kind="positive",
        required_class="normal",
        expected_outcome="PASS",
        task=task,
        expected=expected,
        grant_id=uuid4(),
    )


def plan_data():
    return dict(
        run_id=uuid4(),
        snapshot_hash=HASH,
        review_version=1,
        policy_version="policy-v1",
        policy_hash=HASH,
        profile="record-write-v1",
        confirmed_capabilities=["anchor_record"],
        suite_id="m1-smoke-v1",
        template_version="anchor_record@1",
        planning_time=NOW,
        slots=[slot()],
    )
