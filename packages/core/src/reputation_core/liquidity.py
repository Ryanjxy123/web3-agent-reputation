"""Verify one NPM increase call, without scoring or asserting full task completion."""

import re

from pydantic import BaseModel, ConfigDict, field_serializer

from reputation_core.admission import Verdict

INCREASE_SELECTOR = "219f5d17"
INCREASE_TOPIC = "0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f"


class LiquidityVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    reason: str
    liquidity_delta: int | None = None
    amount0: int | None = None
    amount1: int | None = None
    block_number: int | None = None
    transaction_index: int | None = None

    @field_serializer("liquidity_delta", "amount0", "amount1", when_used="json", return_type=str | None)
    def serialize_quantity(self, value: int | None) -> str | None:
        return str(value) if value is not None else None


class _Contradiction(ValueError):
    pass


def _hex(value: object, digits: int | None = None) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise ValueError("Missing or malformed hex evidence")
    if digits is not None and len(value) != digits + 2:
        raise ValueError("Incorrect hex evidence length")
    return value.lower()


def _same(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise _Contradiction(f"{label} mismatch")


def _words(value: object, count: int) -> list[int]:
    payload = _hex(value, count * 64)[2:]
    return [int(payload[index:index + 64], 16) for index in range(0, len(payload), 64)]


def verify_increase(
    transaction: dict, receipt: dict, *, chain_id: int, expected_sender: str,
    manager: str, token_id: int, expected_tx_hash: str,
    block_timestamp: int | None = None,
) -> LiquidityVerification:
    """Check a final increase step; optional time must come from its trusted block header."""
    observed = {}

    def result(verdict: Verdict, reason: str) -> LiquidityVerification:
        return LiquidityVerification(verdict=verdict, reason=reason, **observed)

    try:
        if type(chain_id) is not int or chain_id < 0 or type(token_id) is not int or not 0 <= token_id < 2**256:
            raise ValueError("Invalid expected chain or token identifier")
        if block_timestamp is not None and (type(block_timestamp) is not int or block_timestamp < 0):
            raise ValueError("Invalid trusted block timestamp")
        sender, target, expected_hash = _hex(expected_sender, 40), _hex(manager, 40), _hex(expected_tx_hash, 64)
        _same(int(_hex(transaction["chainId"]), 16), chain_id, "Transaction chain")
        if "chainId" in receipt:
            _same(int(_hex(receipt["chainId"]), 16), chain_id, "Receipt chain")
        _same(_hex(transaction["hash"], 64), expected_hash, "Transaction hash")
        _same(_hex(receipt["transactionHash"], 64), expected_hash, "Receipt transaction hash")
        for record, label in ((transaction, "Transaction"), (receipt, "Receipt")):
            _same(_hex(record["from"], 40), sender, f"{label} sender")
            _same(_hex(record["to"], 40), target, f"{label} target")
        block_hash = _hex(transaction["blockHash"], 64)
        _same(_hex(receipt["blockHash"], 64), block_hash, "Receipt block hash")
        block = int(_hex(transaction["blockNumber"]), 16)
        index = int(_hex(transaction["transactionIndex"]), 16)
        observed.update(block_number=block, transaction_index=index)
        _same(int(_hex(receipt["blockNumber"]), 16), block, "Receipt block number")
        _same(int(_hex(receipt["transactionIndex"]), 16), index, "Receipt transaction index")
        status = int(_hex(receipt["status"]), 16)
        if status == 0:
            return result(Verdict.FAIL, "The expected sender's transaction to the expected manager reverted")
        if status != 1:
            raise ValueError("Invalid receipt status")
        calldata = _hex(transaction["input"])
        if len(calldata) < 10:
            raise ValueError("Missing call selector")
        _same(calldata[2:10], INCREASE_SELECTOR, "Increase selector")
        actual_token, desired0, desired1, minimum0, minimum1, deadline = _words("0x" + calldata[10:], 6)
        _same(actual_token, token_id, "Call token identifier")
        if minimum0 > desired0 or minimum1 > desired1:
            raise _Contradiction("Call minimum exceeds desired token amount")
        if block_timestamp is not None and block_timestamp > deadline:
            raise _Contradiction("Block timestamp exceeds the call deadline")
        logs = receipt["logs"]
        if not isinstance(logs, list):
            raise ValueError("Receipt logs are missing or malformed")
        manager_events = []
        for log in logs:
            if _hex(log["address"], 40) != target:
                continue
            topics = log["topics"]
            if not isinstance(topics, list):
                raise ValueError("Event topics are malformed")
            if not topics or _hex(topics[0], 64) != INCREASE_TOPIC:
                continue
            if len(topics) != 2:
                raise ValueError("Increase event requires one indexed token identifier")
            manager_events.append((log, int(_hex(topics[1], 64), 16)))
        matching = [log for log, event_token in manager_events if event_token == token_id]
        if not matching:
            if manager_events:
                raise _Contradiction("Increase event token identifier mismatch")
            raise ValueError("No matching IncreaseLiquidity event evidence")
        if len(matching) != 1:
            raise ValueError("Multiple matching IncreaseLiquidity events are ambiguous")
        event = matching[0]
        _same(_hex(event["transactionHash"], 64), expected_hash, "Event transaction hash")
        _same(_hex(event["blockHash"], 64), block_hash, "Event block hash")
        _same(int(_hex(event["blockNumber"]), 16), block, "Event block number")
        _same(int(_hex(event["transactionIndex"]), 16), index, "Event transaction index")
        _hex(event["logIndex"])
        if event["removed"] is not False:
            raise ValueError("Event is removed or has no canonical removal status")
        liquidity, amount0, amount1 = _words(event["data"], 3)
        observed.update(liquidity_delta=liquidity, amount0=amount0, amount1=amount1)
        if not 0 < liquidity < 2**128:
            raise _Contradiction("Event does not show a positive uint128 liquidity increase")
        if not minimum0 <= amount0 <= desired0 or not minimum1 <= amount1 <= desired1:
            raise _Contradiction("Event token amounts violate the call's desired/minimum bounds")
    except _Contradiction as error:
        return result(Verdict.FAIL, str(error))
    except (KeyError, TypeError, ValueError) as error:
        return result(Verdict.UNKNOWN, f"Incomplete or malformed evidence: {error}")
    timing = "deadline checked against supplied block time" if block_timestamp is not None else "deadline not independently checked: block time not supplied"
    return result(Verdict.PASS, f"Final increase call matches sender, target, token, event and amount bounds; {timing}. Full task completion and finality are outside this result")
