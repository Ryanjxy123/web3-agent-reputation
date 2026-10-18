"""Verify a retained BSC wrap/single-pool swap/increase sequence, without network or scoring."""

from math import isfinite
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from reputation_core.admission import Verdict
from reputation_core.liquidity import INCREASE_TOPIC, verify_increase

WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
CAKE = "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82"
ROUTER = "0x1b81d678ffb9c0263b24a97847620c99d213eb14"
MANAGER = "0x46a15b0b27311cedf172ab29e4f4766fbe7f4364"
DEPOSIT = "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SWAP = "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83"
ROLES = ("wrap", "swap", "increase")


class StepVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["wrap", "swap", "increase"]
    verdict: Verdict
    reason: str
    transaction_hash: str | None = None
    block_number: int | None = None
    transaction_index: int | None = None
    block_timestamp: int | None = None
    amount_in: str | None = None
    amount_out: str | None = None
    amount0: str | None = None
    amount1: str | None = None
    liquidity_delta: str | None = None


class BehaviorVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: Verdict
    reason: str
    wrap: StepVerification
    swap: StepVerification
    increase: StepVerification
    elapsed_seconds: int | None = None


class _Contradiction(ValueError):
    pass


class _Unsupported(ValueError):
    pass


def _hex(value: object, digits: int | None = None) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise ValueError("Missing or malformed hexadecimal evidence")
    if digits is not None and len(value) != digits + 2:
        raise ValueError("Incorrect hexadecimal evidence length")
    return value.lower()


def _quantity(value: object) -> int:
    return int(_hex(value), 16)


def _same(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise _Contradiction(f"{label} mismatch")


def _words(value: object, count: int) -> list[int]:
    data = _hex(value, count * 64)[2:]
    return [int(data[index:index + 64], 16) for index in range(0, len(data), 64)]


def _address_word(value: int) -> str:
    if value >= 2**160:
        raise ValueError("Noncanonical address word")
    return "0x" + f"{value:040x}"


def _topic_address(value: object) -> str:
    return _address_word(int(_hex(value, 64), 16))


def _signed(value: int) -> int:
    return value - 2**256 if value >= 2**255 else value


def _bind(
    step: StepVerification, proof: dict, *, expected_hash: str, sender: str,
    chain_id: int, head: int | None, confirmations: int,
    started_at: int | float, window: int,
) -> tuple[dict, dict]:
    tx, receipt, block = proof["transaction"], proof["receipt"], proof["block"]
    step.transaction_hash = _hex(tx["hash"], 64)
    _same(step.transaction_hash, expected_hash, "Published transaction hash")
    _same(_hex(receipt["transactionHash"], 64), expected_hash, "Receipt transaction hash")
    _same(_quantity(tx["chainId"]), chain_id, "Transaction chain")
    if "chainId" in receipt:
        _same(_quantity(receipt["chainId"]), chain_id, "Receipt chain")
    for record, label in ((tx, "Transaction"), (receipt, "Receipt")):
        _same(_hex(record["from"], 40), sender, f"{label} sender")
    _same(_hex(receipt["to"], 40), _hex(tx["to"], 40), "Receipt target")
    block_hash = _hex(tx["blockHash"], 64)
    for record, name in ((receipt, "Receipt"), (block, "Header")):
        _same(_hex(record["blockHash"] if name == "Receipt" else record["hash"], 64),
              block_hash, f"{name} block hash")
    step.block_number = _quantity(tx["blockNumber"])
    step.transaction_index = _quantity(tx["transactionIndex"])
    _same(_quantity(receipt["blockNumber"]), step.block_number, "Receipt block number")
    _same(_quantity(block["number"]), step.block_number, "Header block number")
    _same(_quantity(receipt["transactionIndex"]), step.transaction_index, "Receipt transaction index")
    if not isinstance(block["transactions"], list):
        raise ValueError("Header transaction list is missing")
    if step.transaction_index >= len(block["transactions"]):
        raise _Contradiction("Transaction index is absent from its block")
    _same(_hex(block["transactions"][step.transaction_index], 64), expected_hash,
          "Header transaction at the stated index")
    step.block_timestamp = _quantity(block["timestamp"])
    if not started_at <= step.block_timestamp <= started_at + window:
        raise _Contradiction("Transaction falls outside the published task window")
    status = _quantity(receipt["status"])
    if status == 0:
        raise _Contradiction("The expected executor's transaction reverted")
    if status != 1:
        raise ValueError("Malformed receipt status")
    if type(head) is not int or head - step.block_number < confirmations:
        raise ValueError("Independent confirmation height is missing or insufficient")
    if not isinstance(receipt["logs"], list):
        raise ValueError("Receipt logs are missing")
    indices = []
    for log in receipt["logs"]:
        _hex(log["address"], 40)
        _same(_hex(log["transactionHash"], 64), expected_hash, "Log transaction hash")
        _same(_hex(log["blockHash"], 64), block_hash, "Log block hash")
        _same(_quantity(log["blockNumber"]), step.block_number, "Log block number")
        _same(_quantity(log["transactionIndex"]), step.transaction_index, "Log transaction index")
        if log["removed"] is not False:
            raise ValueError("Log is removed or lacks canonical removal status")
        indices.append(_quantity(log["logIndex"]))
    if len(set(indices)) != len(indices) or indices != sorted(indices):
        raise ValueError("Receipt log indices are duplicated or unordered")
    return tx, receipt


def _events(receipt: dict, address: str, topic: str) -> list[dict]:
    found = []
    for log in receipt["logs"]:
        topics = log["topics"]
        if not isinstance(topics, list):
            raise ValueError("Malformed event topics")
        if _hex(log["address"], 40) == address and topics and _hex(topics[0], 64) == topic:
            found.append(log)
    return found


def _one(events: list[dict], label: str) -> dict:
    if len(events) != 1:
        raise ValueError(f"Missing or ambiguous {label} event")
    return events[0]


def _transfer(receipt: dict, token: str, sender: str, recipient: str, amount: int) -> dict:
    events = _events(receipt, token, TRANSFER)
    matching = []
    for event in events:
        if len(event["topics"]) != 3:
            raise ValueError("Malformed Transfer event")
        if (_topic_address(event["topics"][1]), _topic_address(event["topics"][2])) == (sender, recipient):
            matching.append(event)
    if events and not matching:
        raise _Contradiction("Token Transfer sender or recipient mismatch")
    event = _one(matching, "token Transfer")
    _same(_words(event["data"], 1)[0], amount, "Token Transfer amount")
    return event


def _wrap(step: StepVerification, tx: dict, receipt: dict, sender: str) -> None:
    if _hex(tx["to"], 40) != WBNB or _hex(tx["input"]) != "0xd0e30db0":
        raise _Unsupported("Only a direct WBNB deposit is adapted")
    value = _quantity(tx["value"])
    if value <= 0:
        raise _Contradiction("WBNB deposit has no positive native input")
    event = _one(_events(receipt, WBNB, DEPOSIT), "WBNB Deposit")
    if len(event["topics"]) != 2:
        raise ValueError("Malformed WBNB Deposit event")
    _same(_topic_address(event["topics"][1]), sender, "WBNB Deposit owner")
    _same(_words(event["data"], 1)[0], value, "WBNB Deposit versus transaction value")
    step.amount_in = step.amount_out = str(value)
    step.verdict, step.reason = Verdict.PASS, "Native input equals the executor's canonical WBNB Deposit"


def _swap(step: StepVerification, tx: dict, receipt: dict, sender: str,
          pool: str | None, pool_block: int | None) -> None:
    if _hex(tx["to"], 40) != ROUTER or _hex(tx["input"])[:10] != "0x414bf389":
        raise _Unsupported("Only PancakeSwap V3 exactInputSingle is adapted")
    values = _words("0x" + tx["input"][10:], 8)
    token_in, token_out = _address_word(values[0]), _address_word(values[1])
    if {token_in, token_out} != {WBNB, CAKE}:
        raise _Unsupported("Only the known WBNB/CAKE token pair is adapted")
    _same((token_in, token_out), (WBNB, CAKE), "Swap token direction")
    fee, recipient, deadline, amount_in, minimum_out, limit = values[2:]
    _same(fee, 500, "Swap fee tier")
    _same(_address_word(recipient), sender, "Swap recipient")
    _same(_quantity(tx["value"]), 0, "ERC-20 swap native value")
    if limit != 0:
        raise _Unsupported("A nonzero sqrtPriceLimitX96 can partially fill; this path is not adapted")
    if step.block_timestamp > deadline or amount_in <= 0:
        raise _Contradiction("Swap deadline expired or input amount is not positive")
    if pool is None or pool_block != step.block_number:
        raise ValueError("Independent factory pool lookup for the fixed swap block is missing")
    pool = _hex(pool, 40)
    if int(pool, 16) == 0:
        raise ValueError("Independent factory lookup returned no pool")
    events = _events(receipt, pool, SWAP)
    if not events and any(log["topics"] and _hex(log["topics"][0], 64) == SWAP
                          for log in receipt["logs"]):
        raise _Contradiction("Pool Swap emitter differs from the independent factory pool")
    event = _one(events, "trusted PancakeSwap pool Swap")
    if len(event["topics"]) != 3:
        raise ValueError("Malformed PancakeSwap Swap topics")
    _same(_topic_address(event["topics"][1]), ROUTER, "Pool Swap caller")
    _same(_topic_address(event["topics"][2]), sender, "Pool Swap recipient")
    # PancakeSwap V3 adds two protocol-fee words to the five common Swap words.
    amount0, amount1, *_ = _words(event["data"], 7)
    amount0, amount1 = _signed(amount0), _signed(amount1)
    if amount0 >= 0 or amount1 <= 0:
        raise _Contradiction("Pool Swap signed amounts contradict WBNB-to-CAKE direction")
    _same(amount1, amount_in, "Pool Swap must consume the full exact input")
    amount_out = -amount0
    if amount_out < minimum_out:
        raise _Contradiction("Actual output violates amountOutMinimum")
    incoming = _transfer(receipt, WBNB, sender, pool, amount_in)
    outgoing = _transfer(receipt, CAKE, pool, sender, amount_out)
    if max(_quantity(incoming["logIndex"]), _quantity(outgoing["logIndex"])) >= _quantity(event["logIndex"]):
        raise _Contradiction("Token transfers do not precede the pool Swap event")
    step.amount_in, step.amount_out = str(amount_in), str(amount_out)
    step.verdict, step.reason = Verdict.PASS, "Fixed-block factory pool, full input and positive received output match calldata and token transfers"


def _increase(step: StepVerification, tx: dict, receipt: dict, sender: str,
              expected_hash: str, chain_id: int, token_id: int, pool: str | None) -> None:
    verified = verify_increase(tx, receipt, chain_id=chain_id, expected_sender=sender,
                               manager=MANAGER, token_id=token_id, expected_tx_hash=expected_hash,
                               block_timestamp=step.block_timestamp)
    step.verdict, step.reason = verified.verdict, verified.reason
    for name in ("liquidity_delta", "amount0", "amount1"):
        value = getattr(verified, name)
        setattr(step, name, str(value) if value is not None else None)
    if verified.verdict != Verdict.PASS:
        return
    if pool is None:
        raise ValueError("Independent factory pool evidence is missing")
    pool = _hex(pool, 40)
    _same(_quantity(tx["value"]), 0, "ERC-20 increase native value")
    for token, amount in ((CAKE, verified.amount0), (WBNB, verified.amount1)):
        if amount:
            _transfer(receipt, token, sender, pool, amount)
    event = _one(_events(receipt, MANAGER, INCREASE_TOPIC), "NPM IncreaseLiquidity")
    for token in (CAKE, WBNB):
        for transfer in _events(receipt, token, TRANSFER):
            if _quantity(transfer["logIndex"]) >= _quantity(event["logIndex"]):
                raise _Contradiction("Token transfer does not precede IncreaseLiquidity")
    step.reason = "Final NPM increase and known CAKE/WBNB transfers match its amounts, recipient pool and deadline"


def verify_behavior(
    steps: dict, *, expected_tx_hashes: dict[str, str], expected_sender: str,
    token_id: int, trusted_pool: str | None, trusted_pool_block: int | None,
    confirmation_head: int | None, task_started_at: int | float,
    chain_id: int = 56, task_window_seconds: int = 300, confirmation_distance: int = 64,
) -> BehaviorVerification:
    """Pool and its block must come from an outer independently verified factory read.

    Checks published operations, not provenance of fungible funds, optimality or asset safety.
    Header timestamps are integer seconds; the published task start may retain milliseconds.
    """
    results = {}
    for role in ROLES:
        result = StepVerification(role=role, verdict=Verdict.UNKNOWN, reason="Not evaluated")
        try:
            if (chain_id != 56 or type(task_started_at) not in (int, float) or not isfinite(task_started_at)
                    or task_window_seconds <= 0 or confirmation_distance < 0):
                raise ValueError("Unsupported chain or invalid task time/confirmation policy")
            sender, expected_hash = _hex(expected_sender, 40), _hex(expected_tx_hashes[role], 64)
            tx, receipt = _bind(result, steps[role], expected_hash=expected_hash, sender=sender,
                                chain_id=chain_id, head=confirmation_head, confirmations=confirmation_distance,
                                started_at=task_started_at, window=task_window_seconds)
            if role == "wrap":
                _wrap(result, tx, receipt, sender)
            elif role == "swap":
                _swap(result, tx, receipt, sender, trusted_pool, trusted_pool_block)
            else:
                _increase(result, tx, receipt, sender, expected_hash, chain_id, token_id, trusted_pool)
        except _Contradiction as error:
            result.verdict, result.reason = Verdict.FAIL, str(error)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            result.verdict, result.reason = Verdict.UNKNOWN, f"Missing evidence or unadapted path: {error}"
        results[role] = result
    if any(result.verdict == Verdict.FAIL for result in results.values()):
        verdict, reason = Verdict.FAIL, "At least one published operation contradicts its bound chain evidence"
    elif any(result.verdict != Verdict.PASS for result in results.values()):
        verdict, reason = Verdict.UNKNOWN, "The three-operation sequence has missing evidence or an unadapted path"
    else:
        order = [(results[role].block_number, results[role].transaction_index) for role in ROLES]
        times = [results[role].block_timestamp for role in ROLES]
        if not order[0] < order[1] < order[2] or times != sorted(times):
            verdict, reason = Verdict.FAIL, "Canonical transaction order or header time contradicts wrap, swap, increase order"
        else:
            verdict, reason = Verdict.PASS, "All three published operations match the executor, canonical events, amount bounds, task window, order and confirmation distance"
    times = [result.block_timestamp for result in results.values() if result.block_timestamp is not None]
    return BehaviorVerification(verdict=verdict, reason=reason, **results,
                                elapsed_seconds=max(times) - min(times) if len(times) == 3 else None)
