"""Pure constructed fixtures, separate from the saved live Akashi PoC evidence."""

import json
from copy import deepcopy

import pytest
from eth_abi import encode
from reputation_core.evidence import hash_bytes

from scripts.akashi_assertions import EVENT_TOPIC, normalize_proof, verify_proof

TX = "0xd01d3e019906321b7d410538aebb696dec806df1099756ec85ac7b2da91df7fc"
BLOCK_HASH = "0x7fac88cd6a36477694cf4ad48f4dab316b33f5c759e03a4df87df9f82f16016a"
CID = "be44340d151cbfa7a5dc59b579dd6632fb0891b573f8fdc927264309a3b168f0"
PAYER = "0x0230c6dd5db1d3f871386a3ce1a5a836b2590044"
ETH = "0xeed9d0f7265892e84e43d05da464c75add199260"
USDC = "0xe0c6bb0914be3e49e13ffbc389cf659871a1bcd3"
OTHER_TX = "0x" + "dd" * 32
OTHER_ADDRESS = "0x" + "ee" * 20
BLOCK_NUMBER = 38158156
TIMESTAMP = 1763105659
TYPES = ("string", "string", "address", "uint256", "uint256")
# Golden ABI bytes and topics are fixed independently of the verifier's decoder.
DATA = (
    "0x00000000000000000000000000000000000000000000000000000000000000a0"
    "0000000000000000000000000000000000000000000000000000000000000100"
    "0000000000000000000000000230c6dd5db1d3f871386a3ce1a5a836b2590044"
    "000000000000000000000000000000000000000000000000000000006916db7b"
    "000000000000000000000000000000000000000000000000000089556d5c7000"
    "0000000000000000000000000000000000000000000000000000000000000040"
    "626534343334306431353163626661376135646335396235373964643636333266"
    "62303839316235373366386664633932373236343330396133623136386630"
    "0000000000000000000000000000000000000000000000000000000000000013"
    "67356e75746c6a777761616d6478652e706e6700000000000000000000000000"
)
TOPICS = [
    "0xee4bb5bb21d0486d2baa52a5fdb588a13c6b3a9120b0d14a99303ffd89695e51",
    "0xdc63276fea89655b072073ce87bf6c5798e33781143c66eeabe02d8313ab132a",
]


@pytest.fixture
def service():
    return {
        "tx": TX,
        "anchored": True,
        "proofs": [
            {
                "hash": CID,
                "filename": "g5nutljwwaamdxe.png",
                "submitter": PAYER,
                "timestamp": TIMESTAMP,
                "paid": "151000000000000",
                "currency": "ETH",
                "chain": "base",
                "chainId": 8453,
                "contract": ETH,
                "txHash": TX,
                "blockNumber": BLOCK_NUMBER,
            }
        ],
    }


@pytest.fixture
def evidence():
    position = {
        "blockHash": BLOCK_HASH,
        "blockNumber": hex(BLOCK_NUMBER),
        "transactionIndex": "0x10a",
    }
    addresses = {"from": PAYER, "to": ETH}
    block = {"number": hex(BLOCK_NUMBER), "hash": BLOCK_HASH, "timestamp": hex(TIMESTAMP)}
    return {
        "chain_id": "0x2105",
        "head": {"number": hex(BLOCK_NUMBER + 11), "hash": "0x" + "99" * 32},
        "receipt_block": deepcopy(block),
        "canonical_block": deepcopy(block),
        "tx": {"hash": TX, "chainId": "0x2105", "input": "0x", **addresses, **position},
        "receipt": {
            "transactionHash": TX,
            "status": "0x1",
            **addresses,
            **position,
            "logs": [
                {
                    "transactionHash": TX,
                    "address": ETH,
                    "data": DATA,
                    "topics": list(TOPICS),
                    "removed": False,
                    "logIndex": "0x2cb",
                    **position,
                }
            ],
        },
    }


def verify(service, evidence, query=None):
    return verify_proof(service, query or {"tx": TX}, evidence)


def assert_unknown(result, reason=None):
    assert result["status"] == "UNKNOWN"
    if reason is not None:
        assert result["reason"] == reason
    assert result["confirmed_proofs"] == []
    assert not any(item["status"] == "FAIL" for item in result["assertions"])


def test_golden_eth_proof_passes_at_exact_confirmation_boundary(service, evidence):
    assert EVENT_TOPIC == TOPICS[0]
    result = verify(service, evidence)
    assert result["status"] == "PASS"
    assert result["reason"] == "BUSINESS_EVENT_CONFIRMED"
    assert result["confirmations"] == 12
    assert result["confirmed_proofs"] == service["proofs"]
    assert all(item["status"] == "PASS" for item in result["assertions"])


def test_usdc_submitter_is_payer_and_can_differ_from_relayer(service, evidence):
    service["proofs"][0].update(contract=USDC, currency="USDC", paid="1000000")
    evidence["tx"].update(to=USDC, **{"from": OTHER_ADDRESS})
    evidence["receipt"].update(to=USDC, **{"from": OTHER_ADDRESS})
    log = evidence["receipt"]["logs"][0]
    log["address"] = USDC
    log["data"] = (
        "0x" + encode(TYPES, (CID, "g5nutljwwaamdxe.png", PAYER, TIMESTAMP, 1000000)).hex()
    )
    assert verify(service, evidence)["status"] == "PASS"


def test_all_official_events_are_verified_with_order_independent_service_claims(service, evidence):
    second = deepcopy(service["proofs"][0])
    second.update(hash="aa" * 32, filename="another.txt", paid="0")
    log = deepcopy(evidence["receipt"]["logs"][0])
    log.update(logIndex="0x2cc", topics=[TOPICS[0], hash_bytes(second["hash"].encode())])
    log["data"] = (
        "0x" + encode(TYPES, (second["hash"], second["filename"], PAYER, TIMESTAMP, 0)).hex()
    )
    evidence["receipt"]["logs"].append(log)
    service["proofs"].insert(0, second)
    result = verify(service, evidence)
    assert result["status"] == "PASS" and len(result["confirmed_proofs"]) == 2
    service["proofs"].pop(0)
    assert verify(service, evidence)["status"] == "FAIL"


def test_http_mcp_business_fields_ignore_urls_and_proof_order(service):
    second = deepcopy(service["proofs"][0])
    second.update(hash="aa" * 32, filename="another.txt")
    service["proofs"].append(second)
    http = deepcopy(service)
    http["proofs"].reverse()
    for proof in http["proofs"]:
        proof.update(
            timestampIso="representation only", explorerUrl="ignored", certificateUrl="ignored"
        )
        proof["hash"] = "0x" + proof["hash"].upper()
        for field in ("submitter", "contract", "txHash"):
            proof[field] = "0x" + proof[field][2:].upper()
    mcp = {"structuredContent": http, "content": [{"type": "text", "text": json.dumps(service)}]}
    assert normalize_proof(mcp, mcp=True) == normalize_proof(service)


@pytest.mark.parametrize("contents", [None, {}, "text", [None], [{"type": "text", "text": 1}]])
def test_mcp_malformed_content_is_rejected(service, contents):
    with pytest.raises(ValueError):
        normalize_proof({"structuredContent": service, "content": contents}, mcp=True)


def test_mcp_conflicting_or_duplicate_json_fields_are_rejected(service):
    contradictory = deepcopy(service)
    contradictory["anchored"] = False
    with pytest.raises(ValueError, match="CONFLICTING"):
        normalize_proof(
            {
                "structuredContent": service,
                "content": [{"type": "text", "text": json.dumps(contradictory)}],
            },
            mcp=True,
        )
    with pytest.raises(ValueError):
        normalize_proof(
            {
                "content": [
                    {
                        "type": "text",
                        "text": '{"anchored":true,"anchored":false,"proofs":[]}',
                    }
                ]
            },
            mcp=True,
        )


@pytest.mark.parametrize("value", [{}, {"content": []}, {"isError": True}, {"isError": 1}])
def test_mcp_missing_or_error_proof_is_rejected(value):
    with pytest.raises(ValueError):
        normalize_proof(value, mcp=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", True),
        ("chainId", True),
        ("blockNumber", False),
        ("paid", True),
        ("paid", 1),
        ("paid", "01"),
        ("paid", "-1"),
        ("hash", "bad"),
        ("filename", None),
        ("timestamp", -1),
        ("timestamp", 2**256),
    ],
)
def test_normalization_keeps_strict_business_field_types(service, field, value):
    service["proofs"][0][field] = value
    with pytest.raises(ValueError):
        normalize_proof(service)


@pytest.mark.parametrize(
    "field",
    ["hash", "submitter", "timestamp", "paid", "chainId", "contract", "txHash", "blockNumber"],
)
def test_missing_fields_have_a_value_error_boundary(service, field):
    del service["proofs"][0][field]
    with pytest.raises(ValueError):
        normalize_proof(service)


@pytest.mark.parametrize(
    "scope,reason",
    [
        ({"searched": [USDC], "unsearched": [ETH]}, "SEARCH_INCOMPLETE"),
        ({"searched": [USDC, ETH]}, "GLOBAL_ABSENCE_NOT_ESTABLISHED"),
    ],
)
def test_negative_hash_response_cannot_prove_global_absence(scope, reason):
    response = {"hash": "ab" * 32, "anchored": False, "proofs": [], **scope}
    assert_unknown(verify(response, {}, {"hash": "ab" * 32}), reason)


def test_hash_positive_requires_digest_and_all_transactions_verified(service, evidence):
    service.pop("tx")
    service["hash"] = CID
    assert verify(service, evidence, {"hash": CID})["status"] == "PASS"
    other = deepcopy(service["proofs"][0])
    other["txHash"] = OTHER_TX
    service["proofs"].append(other)
    assert_unknown(verify(service, evidence, {"hash": CID}), "ADDITIONAL_TRANSACTIONS_NOT_VERIFIED")


@pytest.mark.parametrize(
    "field,value",
    [
        ("hash", "ab" * 32),
        ("filename", "wrong.txt"),
        ("submitter", OTHER_ADDRESS),
        ("timestamp", TIMESTAMP + 1),
        ("paid", "0"),
        ("currency", "USDC"),
        ("chain", "ethereum"),
        ("chainId", 1),
        ("contract", USDC),
        ("txHash", OTHER_TX),
        ("blockNumber", BLOCK_NUMBER + 1),
    ],
)
def test_complete_trusted_rpc_confirms_service_business_mismatches(service, evidence, field, value):
    service["proofs"][0][field] = value
    result = verify(service, evidence)
    assert result["status"] == "FAIL" and result["reason"] == "PROOF_EVENT_MISMATCH"
    assert result["confirmed_proofs"] == []


def test_query_echo_and_anchored_claim_are_independent_assertions(service, evidence):
    service["tx"] = OTHER_TX
    result = verify(service, evidence)
    assert result["status"] == "FAIL" and result["reason"] == "RESPONSE_QUERY_MISMATCH"
    service["tx"] = TX
    service["anchored"] = False
    result = verify(service, evidence)
    assert result["status"] == "FAIL" and result["reason"] == "ANCHOR_CLAIM_MISMATCH"


@pytest.mark.parametrize("receipt_status", ["0x0", "0x1"])
def test_receipt_success_alone_cannot_establish_a_proof(service, evidence, receipt_status):
    evidence["receipt"].update(status=receipt_status, logs=[])
    assert verify(service, evidence)["status"] == "FAIL"
    service.update(anchored=False, proofs=[])
    result = verify(service, evidence)
    assert result["status"] == "PASS" and result["confirmed_proofs"] == []
    assert result["reason"] == "TRANSACTION_ABSENCE_CONFIRMED"


def test_reverted_receipt_with_logs_is_an_rpc_contradiction(service, evidence):
    evidence["receipt"]["status"] = "0x0"
    assert_unknown(verify(service, evidence), "EVIDENCE_INCONSISTENT")


@pytest.mark.parametrize(
    "field,value",
    [
        ("transactionHash", OTHER_TX),
        ("blockHash", "0x" + "ab" * 32),
        ("blockNumber", hex(BLOCK_NUMBER + 1)),
        ("transactionIndex", "0x10b"),
    ],
)
def test_every_log_location_is_checked_before_service_conflicts(service, evidence, field, value):
    service["proofs"][0]["hash"] = "ab" * 32
    unrelated = deepcopy(evidence["receipt"]["logs"][0])
    unrelated.update(topics=[], logIndex="0x2cc", data="0x")
    unrelated[field] = value
    evidence["receipt"]["logs"].append(unrelated)
    assert_unknown(verify(service, evidence), "EVIDENCE_INCONSISTENT")


@pytest.mark.parametrize("index,position", [("0x2cb", 1), ("0x2cc", 0)])
def test_duplicate_and_descending_indices_are_rpc_gaps(service, evidence, index, position):
    log = deepcopy(evidence["receipt"]["logs"][0])
    log.update(topics=[], data="0x", logIndex=index)
    evidence["receipt"]["logs"].insert(position, log)
    assert_unknown(verify(service, evidence), "EVIDENCE_INCONSISTENT")


def test_hex_case_differences_and_unrelated_ordered_logs_are_allowed(service, evidence):
    log = evidence["receipt"]["logs"][0]
    for field in ("transactionHash", "blockHash", "blockNumber", "transactionIndex"):
        log[field] = "0x" + log[field][2:].upper()
    unrelated = deepcopy(log)
    unrelated.update(topics=[], data="0x", logIndex="0x2cc")
    evidence["receipt"]["logs"].append(unrelated)
    assert verify(service, evidence)["status"] == "PASS"


@pytest.mark.parametrize(
    "field,value",
    [
        ("removed", True),
        ("removed", 1),
        ("removed", None),
        ("address", "0x11"),
        ("topics", None),
        ("topics", [TOPICS[0]]),
        ("topics", TOPICS + [TOPICS[1]]),
        ("topics", [TOPICS[0], "0x11"]),
        ("data", "0x11"),
        ("data", DATA + "00"),
        ("data", "0xnothex"),
        ("logIndex", "0x02cb"),
    ],
)
def test_bad_or_removed_event_evidence_is_unknown(service, evidence, field, value):
    service["proofs"][0]["filename"] = "service-conflict.txt"
    evidence["receipt"]["logs"][0][field] = value
    assert_unknown(verify(service, evidence))


@pytest.mark.parametrize("issue", ["indexed_cid", "timestamp"])
def test_internal_event_inconsistency_is_unknown(service, evidence, issue):
    log = evidence["receipt"]["logs"][0]
    if issue == "indexed_cid":
        log["topics"][1] = hash_bytes(b"wrong")
    else:
        log["data"] = (
            "0x"
            + encode(
                TYPES, (CID, "g5nutljwwaamdxe.png", PAYER, TIMESTAMP + 1, 151000000000000)
            ).hex()
        )
    assert_unknown(verify(service, evidence), "EVIDENCE_INCONSISTENT")


def test_other_legacy_cid_formats_are_outside_sha256_poc_scope(service, evidence):
    cid = "QmLegacyContentAddressedRecord"
    log = evidence["receipt"]["logs"][0]
    log["topics"][1] = hash_bytes(cid.encode())
    log["data"] = "0x" + encode(TYPES, (cid, "legacy.txt", PAYER, TIMESTAMP, 0)).hex()
    assert_unknown(verify(service, evidence), "UNSUPPORTED_CID_RECORD_FORMAT")


def test_no_transaction_or_receipt_does_not_fabricate_a_positive(service, evidence):
    evidence.update(tx=None, receipt=None)
    assert_unknown(verify(service, evidence), "RECEIPT_NOT_CONFIRMED")


@pytest.mark.parametrize(
    "issue",
    [
        "wrong_chain",
        "wrong_tx_chain",
        "missing_receipt",
        "missing_transaction",
        "missing_block",
        "status",
        "logs",
        "receipt_from",
        "receipt_to",
        "canonical_time",
    ],
)
def test_rpc_gaps_take_priority_over_service_conflicts(service, evidence, issue):
    service["proofs"][0]["paid"] = "0"
    if issue == "wrong_chain":
        evidence["chain_id"] = "0x1"
    elif issue == "wrong_tx_chain":
        evidence["tx"]["chainId"] = "0x1"
    elif issue == "missing_receipt":
        evidence["receipt"] = None
    elif issue == "missing_transaction":
        evidence["tx"] = None
    elif issue == "missing_block":
        del evidence["receipt_block"]
    elif issue == "status":
        evidence["receipt"]["status"] = "0x2"
    elif issue == "logs":
        evidence["receipt"]["logs"] = None
    elif issue.startswith("receipt_"):
        evidence["receipt"][issue.removeprefix("receipt_")] = OTHER_ADDRESS
    else:
        evidence["canonical_block"]["timestamp"] = hex(TIMESTAMP + 1)
    assert_unknown(verify(service, evidence))


@pytest.mark.parametrize("issue", ["eleven", "fork", "head_before_receipt"])
def test_unconfirmed_or_noncanonical_evidence_is_unknown(service, evidence, issue):
    if issue == "eleven":
        evidence["head"]["number"] = hex(BLOCK_NUMBER + 10)
    elif issue == "fork":
        evidence["canonical_block"]["hash"] = "0x" + "ab" * 32
    else:
        evidence["head"]["number"] = hex(BLOCK_NUMBER - 1)
    assert_unknown(verify(service, evidence))


@pytest.mark.parametrize("target", [None, OTHER_ADDRESS])
def test_indirect_target_is_not_a_confirmed_service_failure(service, evidence, target):
    evidence["tx"]["to"] = evidence["receipt"]["to"] = target
    assert_unknown(verify(service, evidence), "INDIRECT_TARGET_NOT_VERIFIED")
    evidence["receipt"]["logs"] = []
    service.update(anchored=False, proofs=[])
    assert verify(service, evidence)["status"] == "PASS"


@pytest.mark.parametrize("query", [{}, {"tx": TX, "hash": CID}, {"tx": "bad"}, {"other": TX}])
def test_malformed_query_cannot_establish_a_result(service, evidence, query):
    assert_unknown(verify_proof(service, query, evidence), "PROOF_OR_QUERY_SCHEMA_INVALID")


def test_deep_mcp_text_json_is_a_protocol_error():
    value = {"content": [{"type": "text", "text": "[" * 20000 + "0" + "]" * 20000}]}
    with pytest.raises(ValueError, match="MCP_JSON_TOO_DEEP"):
        normalize_proof(value, mcp=True)
