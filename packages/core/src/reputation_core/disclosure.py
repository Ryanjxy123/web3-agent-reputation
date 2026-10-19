"""Verify exact increase disclosures against fixed state and complete block logs.

The caller binds both state reads to trusted headers and supplies the complete
block's Increase/Decrease logs for this manager and NFT. This does not verify
swaps, strategy quality, or the Agent's entire capability set.
"""

import re

from pydantic import BaseModel, ConfigDict

from reputation_core.admission import Verdict
from reputation_core.liquidity import INCREASE_TOPIC, _hex, _words, verify_increase

# cast keccak 'DecreaseLiquidity(uint256,uint128,uint256,uint256)'
DECREASE_TOPIC = "0x26f6a048ee9138f2c0ce266f322cb99228e8d619ae2bff30c67f8dcf9d2377b4"


class DisclosureVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: Verdict
    reason: str
    actual_liquidity_after: str | None = None
    declared_liquidity_after: str | None = None
    block_end_liquidity: str | None = None
    actual_amount0_base_units: str | None = None
    actual_amount1_base_units: str | None = None
    declared_amount0: str | None = None
    declared_amount1: str | None = None
    declared_amount0_base_units: str | None = None
    declared_amount1_base_units: str | None = None


def _base_units(value: object, decimals: int) -> int:
    if type(decimals) is not int or not 0 <= decimals <= 255:
        raise ValueError("Independent token decimals must be in 0..255")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        raise ValueError("Disclosure must be an unsigned exact decimal string")
    whole, _, fraction = value.partition(".")
    whole, fraction = whole.lstrip("0") or "0", fraction.rstrip("0")
    if len(whole) > 78 or len(fraction) > decimals:
        raise ValueError("Disclosure exceeds uint256 or token precision")
    units = int(whole) * 10**decimals + int(fraction.ljust(decimals, "0") or "0")
    if units >= 2**256:
        raise ValueError("Disclosure exceeds uint256")
    return units


def _position(value: object) -> list[int]:
    words = _words(value, 12)
    limits = {0: 96, 1: 160, 2: 160, 3: 160, 4: 24, 7: 128, 10: 128, 11: 128}
    if any(words[index] >= 2**bits for index, bits in limits.items()):
        raise ValueError("Position contains an out-of-range ABI value")
    ticks = [word - 2**256 if word >= 2**255 else word for word in words[5:7]]
    if any(not -(2**23) <= tick < 2**23 for tick in ticks) or ticks[0] >= ticks[1]:
        raise ValueError("Position ticks are not canonical ordered int24 values")
    if not 0 < words[2] < words[3] or not words[4]:
        raise ValueError("Position token pair or fee is malformed")
    return words


def verify_disclosure(
    transaction: dict, receipt: dict, *, chain_id: int, expected_sender: str,
    manager: str, token_id: int, expected_tx_hash: str, block_timestamp: int,
    positions_before: str, positions_after: str, block_logs: list[dict],
    declared_liquidity_after: str, declared_amount0: str, declared_amount1: str,
    decimals0: int, decimals1: int, expected_token0: str, expected_token1: str,
) -> DisclosureVerification:
    """Reconstruct target-transaction liquidity, never substitute block-end delta."""
    observed = {name: value for name, value in (
        ("declared_liquidity_after", declared_liquidity_after),
        ("declared_amount0", declared_amount0), ("declared_amount1", declared_amount1),
    ) if isinstance(value, str)}

    def result(verdict: Verdict, reason: str) -> DisclosureVerification:
        return DisclosureVerification(verdict=verdict, reason=reason, **observed)

    if type(block_timestamp) is not int or block_timestamp < 0:
        return result(Verdict.UNKNOWN, "A trusted fixed block timestamp is required")
    increase = verify_increase(
        transaction, receipt, chain_id=chain_id, expected_sender=expected_sender,
        manager=manager, token_id=token_id, expected_tx_hash=expected_tx_hash,
        block_timestamp=block_timestamp,
    )
    if increase.verdict != Verdict.PASS:
        return result(increase.verdict, "Increase step not verified: " + increase.reason)
    observed.update(actual_amount0_base_units=str(increase.amount0),
                    actual_amount1_base_units=str(increase.amount1))
    try:
        before, after = _position(positions_before), _position(positions_after)
        if before[2:7] != after[2:7]:
            raise ValueError("Position token pair, fee or ticks changed between fixed states")
        expected_tokens = [int(_hex(token, 40), 16) for token in (expected_token0, expected_token1)]
        if before[2:4] != expected_tokens:
            raise ValueError("Independent token mapping does not match the position")
        declared_l = _base_units(declared_liquidity_after, 0)
        declared0 = _base_units(declared_amount0, decimals0)
        declared1 = _base_units(declared_amount1, decimals1)
        observed.update(declared_amount0_base_units=str(declared0),
                        declared_amount1_base_units=str(declared1),
                        block_end_liquidity=str(after[7]))
        target, tx_hash = _hex(manager, 40), _hex(expected_tx_hash, 64)
        block_hash = _hex(receipt["blockHash"], 64)
        block_number, target_index = increase.block_number, increase.transaction_index

        def event(log: dict) -> tuple:
            topics = log["topics"]
            if (not isinstance(topics, list) or len(topics) != 2
                or _hex(topics[0], 64) not in (INCREASE_TOPIC, DECREASE_TOPIC)
                or int(_hex(topics[1], 64), 16) != token_id
                or _hex(log["address"], 40) != target
                or _hex(log["blockHash"], 64) != block_hash
                or int(_hex(log["blockNumber"]), 16) != block_number
                or log["removed"] is not False):
                raise ValueError("Block log is outside the fixed manager/token/block scope")
            index = int(_hex(log["transactionIndex"]), 16)
            log_index = int(_hex(log["logIndex"]), 16)
            event_tx = _hex(log["transactionHash"], 64)
            if (event_tx == tx_hash) != (index == target_index):
                raise ValueError("Block log transaction hash/index disagree with the receipt")
            liquidity, amount0, amount1 = _words(log["data"], 3)
            if not 0 < liquidity < 2**128:
                raise ValueError("Block log liquidity is not positive uint128")
            return index, log_index, event_tx, _hex(topics[0], 64), liquidity, amount0, amount1

        if not isinstance(block_logs, list) or not block_logs:
            raise ValueError("Complete same-block liquidity logs were not supplied")
        events = sorted(event(log) for log in block_logs)
        indices = [item[1] for item in events]
        if len(set(indices)) != len(indices) or indices != sorted(indices):
            raise ValueError("Duplicate or inconsistent block log indices")
        transaction_indices, transaction_hashes = {}, {}
        for index, _, event_tx, *_ in events:
            if (transaction_indices.setdefault(event_tx, index) != index
                or transaction_hashes.setdefault(index, event_tx) != event_tx):
                raise ValueError("Block logs disagree on transaction ordering")
        receipt_events = sorted(event(log) for log in receipt["logs"]
                                if _hex(log["address"], 40) == target
                                and log["topics"] and _hex(log["topics"][0], 64) in (INCREASE_TOPIC, DECREASE_TOPIC)
                                and int(_hex(log["topics"][1], 64), 16) == token_id)
        target_events = [item for item in events if item[2] == tx_hash]
        if not target_events or target_events != receipt_events:
            raise ValueError("Same-block logs do not reproduce the target receipt events")
        liquidity, target_after = before[7], None
        for index, _, _, topic, delta, *_ in events:
            liquidity += delta if topic == INCREASE_TOPIC else -delta
            if not 0 <= liquidity < 2**128:
                raise ValueError("Reconstructed liquidity is outside uint128")
            if index == target_index:
                target_after = liquidity
        if liquidity != after[7]:
            raise ValueError("Complete block logs do not reconcile the two fixed position states")
        observed["actual_liquidity_after"] = str(target_after)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        return result(Verdict.UNKNOWN, f"Incomplete or inconsistent independent evidence: {error}")
    if declared0 != increase.amount0 or declared1 != increase.amount1:
        return result(Verdict.FAIL, "Published exact token amounts contradict the verified increase event")
    if declared_l != target_after:
        return result(Verdict.FAIL, "Published liquidity_after contradicts reconstructed target-transaction state")
    return result(Verdict.PASS, "Published exact amounts and liquidity_after match the verified event and ordered fixed-state reconstruction; broader capabilities are not evaluated")
