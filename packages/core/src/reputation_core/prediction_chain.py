"""Pure Gnosis Mech/Omen evidence checks; no network, clocks or scoring."""

import json
import re
from typing import Literal

from eth_hash.auto import keccak
from pydantic import BaseModel, ConfigDict

from reputation_core.admission import Verdict
from reputation_core.reporting import ReportFinding

REGISTRY = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
BRIDGER = "0x6e8f740f23f07ce129daa59786926feca8c2d2f3"
SERVICE_REGISTRY = "0x9338b5153ae39bb89f50468e608ed9d764b755fd"
MARKETPLACE = "0x735faab1c4ec41128c367afb5c3bac73509f70bb"
CT = "0xceafdd6bc0bef976fdcd1112955828e00543c0ce"
PROXY = "0xab16d643ba051c11962da645f74632d3130c81e2"
REALITY = "0x79e32ae03fb27b07c89c0c568f80287c01ca2e57"
MULTISEND = "0xa238cbeb142c10ef7ad8442c6d1f9e89e07e7761"
TEMPLATE = '{"title": "%s", "type": "single-select", "outcomes": [%s], "category": "%s", "lang": "%s"}'
REQUEST_TOPIC = "0x" + keccak(b"Request(address,bytes32,bytes)").hex()
DELIVER_TOPIC = "0x" + keccak(b"Deliver(address,address,bytes32,uint256,bytes)").hex()
MARKET_REQUEST_TOPIC = "0x" + keccak(b"MarketplaceRequest(address,address,uint256,bytes32[],bytes[])").hex()


class PredictionChainVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: Verdict
    reason: str
    checks: list[ReportFinding]
    request_id: str | None = None
    priority_mech: str | None = None
    delivery_mech: str | None = None
    service_id: str | None = None
    operator: str | None = None
    request_block: int | None = None
    delivery_block: int | None = None
    request_timestamp: int | None = None
    delivery_timestamp: int | None = None
    response_timeout: int | None = None
    input_digest: str | None = None
    output_digest: str | None = None
    delivery_rate: str | None = None


class MarketSettlementVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: Verdict
    reason: str
    checks: list[ReportFinding]
    market: str | None = None
    condition_id: str | None = None
    question_id: str | None = None
    title: str | None = None
    question_data: str | None = None
    template_id: str | None = None
    outcomes: list[str] = []
    final_outcome: Literal["yes", "no"] | None = None
    opening_timestamp: int | None = None
    finalized_timestamp: int | None = None
    checked_block: int | None = None
    payouts: list[str] = []


class _Contradiction(ValueError):
    pass


class _Unsupported(ValueError):
    pass


def _hex(value: object, digits: int | None = None) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise ValueError("Missing hexadecimal evidence")
    if digits is not None and len(value) != digits + 2:
        raise ValueError("Incorrect hexadecimal evidence length")
    return value.lower()


def _uint(value: object) -> int:
    return int(_hex(value), 16)


def _same(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise _Contradiction(label)


def _address_word(value: int) -> str:
    if value < 0 or value >= 2**160:
        raise ValueError("Noncanonical address word")
    return "0x" + f"{value:040x}"


def _words(value: object, count: int | None = None) -> list[int]:
    encoded = _hex(value)[2:]
    if len(encoded) % 64 or (count is not None and len(encoded) != count * 64):
        raise ValueError("Noncanonical ABI words")
    return [int(encoded[index:index + 64], 16) for index in range(0, len(encoded), 64)]


def selector(signature: str) -> str:
    return "0x" + keccak(signature.encode("ascii"))[:4].hex()


def calldata(signature: str, *arguments: int | str) -> str:
    words = []
    for argument in arguments:
        number = int(argument, 16) if isinstance(argument, str) else argument
        if type(number) is not int or not 0 <= number < 2**256:
            raise ValueError("Invalid static ABI argument")
        words.append(f"{number:064x}")
    return selector(signature) + "".join(words)


def call_value(calls: dict, name: str, contract: str, data: str, block: int) -> object:
    proof = calls[name]
    _same(proof["method"], "eth_call", "RPC method differs from the required read")
    _same(proof["params"], [{"to": contract, "data": data}, hex(block)], "RPC parameters or fixed block differ")
    return proof["value"]


def _call_uint(calls: dict, name: str, contract: str, data: str, block: int) -> int:
    return _words(call_value(calls, name, contract, data, block), 1)[0]


def _finding(label: str, text: str) -> ReportFinding:
    return ReportFinding(label=label, verdict=Verdict.PASS, explanation=text)


def verify_omen_settlement(evidence: dict, *, snapshot_block: int, snapshot_hash: str) -> MarketSettlementVerification:
    result = MarketSettlementVerification(verdict=Verdict.UNKNOWN, reason="缺少完整市场结算证据。", checks=[])
    try:
        market = result.market = _hex(evidence["market"], 40)
        calls, question, header = evidence["calls"], evidence["question"], evidence["header"]
        _same(_uint(header["number"]), snapshot_block, "Snapshot header height differs")
        _same(_hex(header["hash"], 64), _hex(snapshot_hash, 64), "Snapshot header hash differs")
        result.checked_block = snapshot_block
        question_id = result.question_id = _hex(question["id"], 64)
        template = int(question["templateId"])
        if template != 2:
            raise _Unsupported("Only the published single-select template 2 is supported")
        result.template_id = str(template)
        text = question["data"]
        if not isinstance(text, str):
            raise ValueError("Original Reality question data is missing")
        components = text.split("\u241f")
        if len(components) != 4:
            raise _Unsupported("Unsupported Reality template arguments")
        outcomes = json.loads("[" + components[1] + "]")
        if len(outcomes) != 2 or {value.lower() for value in outcomes if isinstance(value, str)} != {"yes", "no"}:
            raise _Unsupported("The original question is not binary Yes/No")
        result.title, result.question_data, result.outcomes = components[0], text, outcomes
        opening = result.opening_timestamp = _call_uint(calls, "reality-opening", REALITY,
            calldata("getOpeningTS(bytes32)", question_id), snapshot_block)
        if not 0 <= opening < 2**32:
            raise ValueError("Opening timestamp is not uint32")
        content_hash = keccak(template.to_bytes(32) + opening.to_bytes(4) + text.encode("utf-8"))
        _same(_call_uint(calls, "reality-content-hash", REALITY, calldata("getContentHash(bytes32)", question_id), snapshot_block),
              int.from_bytes(content_hash), "Original question content differs from the on-chain hash")
        _same(_call_uint(calls, "reality-template-hash", REALITY, calldata("template_hashes(uint256)", template), snapshot_block),
              int.from_bytes(keccak(TEMPLATE.encode("utf-8"))), "The deployed template differs from the supported template")
        result.checks.append(_finding("原题干与选项", "完整 UTF-8 题干、分隔符及模板哈希与 Reality 链上内容一致，选项顺序已核实。"))
        _same(_address_word(_call_uint(calls, "market-ct", market, calldata("conditionalTokens()"), snapshot_block)), CT,
              "Market ConditionalTokens address differs from the trusted deployment")
        condition = _call_uint(calls, "market-condition", market, calldata("conditionIds(uint256)", 0), snapshot_block)
        condition_id = result.condition_id = "0x" + f"{condition:064x}"
        expected = keccak(bytes.fromhex(PROXY[2:]) + bytes.fromhex(question_id[2:]) + (2).to_bytes(32))
        _same(condition, int.from_bytes(expected), "Market condition does not bind the actual oracle, question and two outcomes")
        _same(_address_word(_call_uint(calls, "proxy-reality", PROXY, calldata("realitio()"), snapshot_block)), REALITY,
              "Proxy uses a different Reality contract")
        _same(_address_word(_call_uint(calls, "proxy-ct", PROXY, calldata("conditionalTokens()"), snapshot_block)), CT,
              "Proxy uses a different ConditionalTokens contract")
        _same(_call_uint(calls, "outcome-count", CT, calldata("getOutcomeSlotCount(bytes32)", condition_id), snapshot_block), 2,
              "The condition is not binary")
        result.checks.append(_finding("市场与问题绑定", "市场的实际条件哈希与已核对的 Proxy、原问题编号和二元选项数量精确匹配。"))
        if _call_uint(calls, "reality-finalized", REALITY, calldata("isFinalized(bytes32)", question_id), snapshot_block) != 1:
            raise ValueError("The oracle is not finalized at the fixed block")
        finalized = result.finalized_timestamp = _call_uint(calls, "reality-finalize-ts", REALITY,
            calldata("getFinalizeTS(bytes32)", question_id), snapshot_block)
        if not opening <= finalized <= _uint(header["timestamp"]):
            raise ValueError("Finalization timestamp is missing or outside the fixed snapshot")
        answer = _call_uint(calls, "reality-answer", REALITY, calldata("resultFor(bytes32)", question_id), snapshot_block)
        denominator = _call_uint(calls, "payout-denominator", CT, calldata("payoutDenominator(bytes32)", condition_id), snapshot_block)
        payouts = [_call_uint(calls, f"payout-{index}", CT, calldata("payoutNumerators(bytes32,uint256)", condition_id, index), snapshot_block)
                   for index in range(2)]
        result.payouts = [str(value) for value in payouts]
        if denominator == 0:
            raise ValueError("The market condition has not been settled")
        _same(sum(payouts), denominator, "Payout numerators do not sum to the on-chain denominator")
        if answer == 2**256 - 1 or payouts[0] == payouts[1]:
            result.verdict, result.reason = Verdict.NOT_APPLICABLE, "该市场为无效或均分结算，不属于本政策的有效二元结果。"
            return result
        if answer not in (0, 1):
            raise _Unsupported("The oracle answer is not a supported binary option")
        _same(payouts[answer], denominator, "Oracle answer differs from the market's winning payout")
        _same(payouts[1 - answer], 0, "The losing payout is nonzero")
        result.final_outcome = outcomes[answer].lower()
        result.checks.append(_finding("最终结算", "固定区块中 Reality 已最终确定，且 ConditionalTokens 的实际支付向量与答案及原始选项顺序一致。"))
        result.verdict, result.reason = Verdict.PASS, "原题干、选项顺序、市场条件及最终二元链上结算已独立绑定。"
    except _Contradiction as error:
        result.verdict, result.reason = Verdict.FAIL, str(error)
    except (_Unsupported, KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
        result.verdict, result.reason = Verdict.UNKNOWN, str(error)
    return result


def _abi_word(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 32 > len(data):
        raise ValueError("Truncated ABI word")
    return int.from_bytes(data[offset:offset + 32])


def _abi_bytes(data: bytes, offset: int, minimum: int = 0) -> bytes:
    if offset % 32 or offset < minimum:
        raise ValueError("Invalid dynamic ABI offset")
    length = _abi_word(data, offset)
    end = offset + 32 + length
    padded = offset + 32 + ((length + 31) // 32) * 32
    if padded > len(data) or any(data[end:padded]):
        raise ValueError("Truncated or noncanonical ABI bytes")
    return data[offset + 32:end]


def _abi_array(data: bytes, offset: int, *, dynamic: bool = False) -> list:
    if offset % 32:
        raise ValueError("Unaligned ABI array")
    count = _abi_word(data, offset)
    if count > 256 or offset + 32 + count * 32 > len(data):
        raise _Unsupported("Unsupported or truncated batch size")
    start = offset + 32
    values = [_abi_word(data, start + index * 32) for index in range(count)]
    return [_abi_bytes(data, start + value, count * 32 + start) for value in values] if dynamic else values


def _receipt(part: dict, head: int) -> tuple[dict, dict, int, int]:
    tx, receipt, header = part["transaction"], part["receipt"], part["header"]
    block, index = _uint(tx["blockNumber"]), _uint(tx["transactionIndex"])
    _same(_uint(tx["chainId"]), 100, "Transaction belongs to another chain")
    _same(_hex(tx["hash"], 64), _hex(receipt["transactionHash"], 64), "Transaction and receipt hashes differ")
    _same(_uint(receipt["blockNumber"]), block, "Receipt block differs")
    _same(_uint(receipt["transactionIndex"]), index, "Receipt index differs")
    _same(_uint(header["number"]), block, "Header height differs")
    _same(_hex(tx["blockHash"], 64), _hex(receipt["blockHash"], 64), "Receipt block hash differs")
    _same(_hex(header["hash"], 64), _hex(tx["blockHash"], 64), "Header block hash differs")
    transactions = header['transactions']
    if not 0 <= index < len(transactions) or _hex(transactions[index], 64) != _hex(tx['hash'], 64):
        raise ValueError('The actual block transaction order does not contain this transaction at its claimed index')
    _same(_hex(receipt["from"], 40), _hex(tx["from"], 40), "Receipt sender differs")
    _same(_hex(receipt["to"], 40), _hex(tx["to"], 40), "Receipt recipient differs")
    if head - block < 64:
        raise ValueError("Insufficient observed confirmation distance")
    if _uint(receipt["status"]) != 1:
        raise _Contradiction("The retained transaction reverted")
    seen = set()
    for log in receipt["logs"]:
        _same(log["removed"], False, "Removed event is not final evidence")
        _same(_hex(log["transactionHash"], 64), _hex(tx["hash"], 64), "Event transaction differs")
        _same(_hex(log["blockHash"], 64), _hex(header["hash"], 64), "Event block hash differs")
        _same(_uint(log["blockNumber"]), block, "Event height differs")
        _same(_uint(log["transactionIndex"]), index, "Event transaction index differs")
        log_index = _uint(log["logIndex"])
        if log_index in seen:
            raise ValueError("Repeated log index")
        seen.add(log_index)
    return tx, receipt, block, _uint(header["timestamp"])


def _inner_calls(tx: dict) -> list[tuple[str, bytes, int]]:
    encoded = bytes.fromhex(_hex(tx["input"])[2:])
    if encoded[:4] != bytes.fromhex(selector("execTransaction(address,uint256,bytes,uint8,uint256,uint256,uint256,address,address,bytes)")[2:]):
        # Direct EOA calls are a separate supported shape; contract sender is checked against operator below.
        return [(_hex(tx["to"], 40), encoded, _uint(tx["value"]))]
    data = encoded[4:]
    target, value, operation = _address_word(_abi_word(data, 0)), _abi_word(data, 32), _abi_word(data, 96)
    inner = _abi_bytes(data, _abi_word(data, 64), 320)
    if operation == 0:
        return [(target, inner, value)]
    if operation != 1 or target != MULTISEND or inner[:4].hex() != "8d80ff0a":
        raise _Unsupported("Unsupported Safe delegatecall target")
    packed = _abi_bytes(inner[4:], _abi_word(inner[4:], 0), 32)
    output, offset = [], 0
    while offset < len(packed):
        if len(packed) - offset < 85:
            raise ValueError("Truncated MultiSend entry")
        op = packed[offset]
        to = "0x" + packed[offset + 1:offset + 21].hex()
        amount = int.from_bytes(packed[offset + 21:offset + 53])
        length = int.from_bytes(packed[offset + 53:offset + 85])
        end = offset + 85 + length
        if end > len(packed) or op != 0:
            raise _Unsupported("Unsupported or truncated MultiSend subcall")
        output.append((to, packed[offset + 85:end], amount))
        offset = end
    return output


def _calling_actor(tx: dict) -> str:
    data = _hex(tx["input"])
    if data[:10] == selector("execTransaction(address,uint256,bytes,uint8,uint256,uint256,uint256,address,address,bytes)"):
        return _hex(tx["to"], 40)
    if _hex(tx["to"], 40) == MARKETPLACE and data[:10] == selector("request(bytes,uint256,bytes32,address,uint256,bytes)"):
        return _hex(tx["from"], 40)
    if data[:10] == selector("deliverToMarketplace(bytes32[],bytes[])"):
        return _hex(tx["from"], 40)
    raise _Unsupported("Unsupported requester/operator call shape")


def _unique_call(tx: dict, target: str, signature: str) -> bytes:
    expected = bytes.fromhex(selector(signature)[2:])
    matches = [data[4:] for to, data, _ in _inner_calls(tx) if to == target and data[:4] == expected]
    if len(matches) != 1:
        raise _Unsupported("Expected exactly one supported business call")
    return matches[0]


def _event(receipt: dict, address: str, topic: str, request: int, id_offset: int = 0) -> dict:
    matches = []
    for log in receipt["logs"]:
        if _hex(log["address"], 40) == address and log["topics"] and _hex(log["topics"][0], 64) == topic:
            if _abi_word(bytes.fromhex(_hex(log["data"])[2:]), id_offset) == request:
                matches.append(log)
    if len(matches) != 1:
        raise ValueError("A unique task-specific event is missing")
    return matches[0]


def extract_task_anchors(evidence: dict, *, mech: str, request_id: str, confirmation_head: int) -> dict:
    """Authenticate indexed CID/time hints before selection, without reading prediction output."""
    request_tx, request_receipt, rb, rt = _receipt(evidence["request"], confirmation_head)
    delivery_tx, delivery_receipt, db, dt = _receipt(evidence["delivery"], confirmation_head)
    if (rb, _uint(request_tx["transactionIndex"])) >= (db, _uint(delivery_tx["transactionIndex"])) or rt > dt:
        raise ValueError("Indexed delivery does not follow its original request")
    rid = int(_hex(request_id, 64), 16)
    requests = [log for log in request_receipt["logs"] if log["topics"] and
                _hex(log["topics"][0], 64) == REQUEST_TOPIC and
                _abi_word(bytes.fromhex(_hex(log["data"])[2:]), 0) == rid]
    if len(requests) != 1:
        raise ValueError("Unique original on-chain request event is missing")
    request = requests[0]
    priority = _hex(request["address"], 40)
    _same(len(request["topics"]), 2, "Request indexed fields differ")
    _same(_address_word(int(request["topics"][1], 16)), priority, "Request event priority differs")
    delivery = _event(delivery_receipt, _hex(mech, 40), DELIVER_TOPIC, rid)
    request_data, delivery_data = [bytes.fromhex(_hex(log["data"])[2:]) for log in (request, delivery)]
    input_digest = _abi_bytes(request_data, _abi_word(request_data, 32), 64)
    output_digest = _abi_bytes(delivery_data, _abi_word(delivery_data, 64), 96)
    if len(input_digest) != 32 or len(output_digest) != 32:
        raise ValueError("Task events do not carry the supported CID digest shape")
    return {"input_digest": "0x" + input_digest.hex(), "output_digest": "0x" + output_digest.hex(),
            "request_timestamp": rt, "delivery_timestamp": dt, "priority_mech": priority,
            "request_block": rb, "delivery_block": db}


def verify_prediction_chain(evidence: dict, *, mech: str, service_id: int, request_id: str,
                            confirmation_head: int) -> PredictionChainVerification:
    """Verify ordinary marketplace request→delivery, including Safe batched calls.

    RPC proof envelopes are reauthenticated by the platform before this pure check.
    Unsupported signed/off-chain requests remain UNKNOWN rather than inheriting this rule.
    """
    result = PredictionChainVerification(verdict=Verdict.UNKNOWN, reason="缺少完整历史履约证据。", checks=[])
    try:
        mech = _hex(mech, 40)
        result.request_id, result.delivery_mech, result.service_id = _hex(request_id, 64), mech, str(service_id)
        rid = int(request_id, 16)
        request_tx, request_receipt, rb, rt = _receipt(evidence["request"], confirmation_head)
        delivery_tx, delivery_receipt, db, dt = _receipt(evidence["delivery"], confirmation_head)
        result.request_block, result.delivery_block = rb, db
        result.request_timestamp, result.delivery_timestamp = rt, dt
        if (rb, _uint(request_tx["transactionIndex"])) >= (db, _uint(delivery_tx["transactionIndex"])) or rt > dt:
            raise _Contradiction("Delivery does not follow its request")
        calls = evidence["calls"]
        before = _words(call_value(calls, "request-info-before", MARKETPLACE,
                                  calldata("mapRequestIdInfos(bytes32)", request_id), db - 1), 6)
        after = _words(call_value(calls, "request-info-after", MARKETPLACE,
                                 calldata("mapRequestIdInfos(bytes32)", request_id), db), 6)
        priority, delivered, requester = [_address_word(value) for value in before[:3]]
        timeout, cap, payment = before[3:]
        if not timeout or not cap:
            raise _Unsupported("Not an ordinary registered marketplace request")
        _same(delivered, "0x" + "0" * 40, "This task was already delivered before the retained transaction")
        _same(after, [before[0], int(mech, 16), *before[2:]], "Marketplace task state does not record this delivery")
        result.priority_mech, result.response_timeout = priority, timeout
        _same(_calling_actor(request_tx), requester, "Actual calling actor differs from the marketplace requester")
        # Request and delivery are distinct actor roles. Outer EOA is the Safe relayer, not the service operator.
        operator = _address_word(_call_uint(calls, "delivery-operator", mech, calldata("getOperator()"), db))
        result.operator = operator
        _same(_calling_actor(delivery_tx), operator, "Delivery transaction does not execute through the historical service operator")
        for phase, block in (("request", rb), ("delivery", db)):
            _same(_call_uint(calls, phase + "-service-id", mech, calldata("serviceId()"), block), service_id,
                  "Historical Mech service identity differs")
            _same(_address_word(_call_uint(calls, phase + "-service-registry", mech, calldata("serviceRegistry()"), block)),
                  SERVICE_REGISTRY, "Historical Mech service registry differs")
        _same(_address_word(_call_uint(calls, "delivery-authorized", MARKETPLACE, calldata("checkMech(address)", mech), db)),
              operator, "Marketplace does not authorize this historical Mech/operator")
        _same(_call_uint(calls, "delivery-payment-type", mech, calldata("paymentType()"), db), payment,
              "Delivery payment type differs from the request")
        if priority != mech and dt <= timeout:
            raise _Contradiction("A different Mech delivered before the exclusive priority window expired")
        result.checks.append(_finding("历史归属与接手边界", "同一服务合约在请求和交付区块均绑定本服务；实际 Safe、授权、支付类型和严格接手时间已核实。"))
        request_event = _event(request_receipt, priority, REQUEST_TOPIC, rid)
        _same(len(request_event["topics"]), 2, "Request event indexed fields differ")
        _same(_address_word(int(request_event["topics"][1], 16)), priority, "Request event Mech differs")
        encoded = bytes.fromhex(_hex(request_event["data"])[2:])
        digest = _abi_bytes(encoded, _abi_word(encoded, 32), 64)
        if len(digest) != 32:
            raise _Unsupported("Request does not contain a supported SHA-256 CID digest")
        result.input_digest = "0x" + digest.hex()
        marketplace_events = []
        for log in request_receipt["logs"]:
            if _hex(log["address"], 40) != MARKETPLACE or not log["topics"] or log["topics"][0].lower() != MARKET_REQUEST_TOPIC:
                continue
            encoded_request = bytes.fromhex(_hex(log["data"])[2:])
            ids = _abi_array(encoded_request, _abi_word(encoded_request, 32))
            if rid in ids:
                marketplace_events.append((log, encoded_request, ids))
        if len(marketplace_events) != 1:
            raise ValueError("Unique MarketplaceRequest task binding is missing")
        marketplace_event, encoded_request, ids = marketplace_events[0]
        _same(len(marketplace_event["topics"]), 3, "MarketplaceRequest indexed fields differ")
        _same(_address_word(int(marketplace_event["topics"][1], 16)), priority, "MarketplaceRequest priority differs")
        _same(_address_word(int(marketplace_event["topics"][2], 16)), requester, "MarketplaceRequest requester differs")
        _same(_abi_word(encoded_request, 0), len(ids), "MarketplaceRequest count differs")
        datas = _abi_array(encoded_request, _abi_word(encoded_request, 64), dynamic=True)
        _same(len(datas), len(ids), "MarketplaceRequest payload count differs")
        if ids.count(rid) != 1:
            raise ValueError("Repeated request ID in MarketplaceRequest")
        _same(datas[ids.index(rid)], digest, "MarketplaceRequest CID differs from the Mech Request")
        request_call = _unique_call(request_tx, MARKETPLACE, "request(bytes,uint256,bytes32,address,uint256,bytes)")
        _same(_abi_bytes(request_call, _abi_word(request_call, 0), 192), digest, "Request calldata and task CID differ")
        _same(_address_word(_abi_word(request_call, 96)), priority, "Request calldata priority differs")
        _same(_abi_word(request_call, 64), payment, "Request calldata payment type differs")
        _same(rt + _abi_word(request_call, 128), timeout, "Absolute task timeout differs from the original request")
        if cap > _abi_word(request_call, 32):
            raise _Contradiction("Recorded rate exceeds requester price cap")
        event = _event(delivery_receipt, mech, DELIVER_TOPIC, rid)
        _same(len(event["topics"]), 3, "Delivery event indexed fields differ")
        _same(_address_word(int(event["topics"][1], 16)), mech, "Delivery event Mech differs")
        _same(_address_word(int(event["topics"][2], 16)), operator, "Delivery event service Safe differs")
        encoded = bytes.fromhex(_hex(event["data"])[2:])
        rate = _abi_word(encoded, 32)
        result.delivery_rate = str(rate)
        if rate > cap:
            raise _Contradiction("Delivery rate exceeds this task's registered cap")
        output_digest = _abi_bytes(encoded, _abi_word(encoded, 64), 96)
        if len(output_digest) != 32:
            raise _Unsupported("Delivery does not contain a supported SHA-256 CID digest")
        result.output_digest = "0x" + output_digest.hex()
        deliver_call = _unique_call(delivery_tx, mech, "deliverToMarketplace(bytes32[],bytes[])")
        ids = _abi_array(deliver_call, _abi_word(deliver_call, 0))
        payloads = _abi_array(deliver_call, _abi_word(deliver_call, 32), dynamic=True)
        _same(len(ids), len(payloads), "Delivery batch arrays differ")
        if ids.count(rid) != 1:
            raise ValueError("Task is missing or repeated in the actual delivery call")
        _same(payloads[ids.index(rid)], output_digest, "Delivery calldata and task output CID differ")
        result.checks.append(_finding("请求与交付原件", "原交易调用与唯一 Request/Deliver 事件按任务编号、CID、区块哈希、交易位置和事件位置精确绑定。"))
        result.verdict, result.reason = Verdict.PASS, "该次历史任务的实际交付归属、完整调用、支付上限和接手规则已核验；不代表预测准确。"
    except _Contradiction as error:
        result.verdict, result.reason = Verdict.FAIL, str(error)
    except (_Unsupported, KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
        result.verdict, result.reason = Verdict.UNKNOWN, str(error)
    return result
