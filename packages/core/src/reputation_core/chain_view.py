"""Deterministic descriptions of retained chain evidence; never a new score."""

import re

from pydantic import BaseModel, ConfigDict

from reputation_core.admission import Verdict
from reputation_core.behavior import CAKE, DEPOSIT, MANAGER, ROUTER, TRANSFER, WBNB
from reputation_core.liquidity import INCREASE_TOPIC


class ChainAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sample_id: str
    chain_id: int
    action: str
    title: str
    transaction_hash: str
    block_number: int
    executor: str
    target: str
    method: str
    summary: str
    verdict: Verdict
    evidence: list[str]


class ReportChainEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    actions: list[ChainAction]
    summary: str
    limitations: list[str]


_METHODS = {
    (56, WBNB, "0xd0e30db0"): ("wrap", "包装原生币", "deposit()"),
    (56, ROUTER, "0x414bf389"): (
        "swap", "兑换资产", "exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))",
    ),
    (56, MANAGER, "0x219f5d17"): (
        "increase_liquidity", "增加仓位流动性", "increaseLiquidity((uint256,uint256,uint256,uint256,uint256,uint256))",
    ),
}
_ASSETS = {(56, WBNB): ("WBNB", 18), (56, CAKE): ("CAKE", 18)}


def _hex(value: object, digits: int | None = None) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise ValueError("Malformed chain evidence hex value")
    if digits is not None and len(value) != digits + 2:
        raise ValueError("Malformed chain evidence hex length")
    return value.lower()


def _quantity(value: object) -> int:
    return int(_hex(value), 16)


def _words(value: object, count: int) -> list[int]:
    data = _hex(value, count * 64)[2:]
    return [int(data[index:index + 64], 16) for index in range(0, len(data), 64)]


def _address(value: int) -> str:
    if value >= 2**160:
        raise ValueError("Noncanonical address word")
    return f"0x{value:040x}"


def _units(value: int, decimals: int) -> str:
    whole, fraction = divmod(value, 10**decimals)
    suffix = f"{fraction:0{decimals}d}".rstrip("0")
    return str(whole) + ("." + suffix if suffix else "")


def _asset(chain_id: int, token: str, amount: int) -> str:
    asset = _ASSETS.get((chain_id, token))
    return f"{asset[0]} {_units(amount, asset[1])}" if asset else f"{token} 的 {amount} 个最小单位"


def has_chain_action_description(transaction: dict) -> bool:
    """Recognized protocol call, independent of Agent name or scoring policy."""
    try:
        key = (_quantity(transaction["chainId"]), _hex(transaction["to"], 40), transaction["input"][:10].lower())
    except (KeyError, TypeError, ValueError):
        return False
    return key in _METHODS


def _transfers(receipt: dict) -> list[tuple[str, str, str, int]]:
    transfers = []
    for event in receipt["logs"]:
        topics = event.get("topics", [])
        if len(topics) == 3 and topics[0].lower() == TRANSFER:
            transfers.append((
                _hex(event["address"], 40), _address(int(_hex(topics[1], 64), 16)),
                _address(int(_hex(topics[2], 64), 16)), _words(event["data"], 1)[0],
            ))
    return transfers


def describe_chain_action(
    transaction: dict, receipt: dict, block: dict, *, sample_id: str,
    verdict: Verdict, evidence: list[str],
) -> ChainAction:
    """Bind the three raw RPC records and explain their actual calldata/events.

    The published sample verdict supplies attribution and historical rule results.
    This view does not repeat its full task, authorization or confirmation checks.
    """
    tx_hash = _hex(transaction["hash"], 64)
    block_hash = _hex(transaction["blockHash"], 64)
    block_number = _quantity(transaction["blockNumber"])
    tx_index = _quantity(transaction["transactionIndex"])
    sender, target = _hex(transaction["from"], 40), _hex(transaction["to"], 40)
    chain_id = _quantity(transaction["chainId"])
    if (
        _hex(receipt["transactionHash"], 64) != tx_hash
        or _hex(receipt["blockHash"], 64) != block_hash
        or _hex(block["hash"], 64) != block_hash
        or _quantity(receipt["blockNumber"]) != block_number
        or _quantity(block["number"]) != block_number
        or _quantity(receipt["transactionIndex"]) != tx_index
        or _hex(receipt["from"], 40) != sender
        or _hex(receipt["to"], 40) != target
    ):
        raise ValueError("Transaction, receipt and block evidence do not match")
    block_transactions = block["transactions"]
    if not isinstance(block_transactions, list) or tx_index >= len(block_transactions):
        raise ValueError("Transaction is absent from the cited block")
    member = block_transactions[tx_index]
    if _hex(member["hash"] if isinstance(member, dict) else member, 64) != tx_hash:
        raise ValueError("Transaction index disagrees with the cited block")
    for event in receipt["logs"]:
        if (
            _hex(event["transactionHash"], 64) != tx_hash
            or _hex(event["blockHash"], 64) != block_hash
            or _quantity(event["blockNumber"]) != block_number
            or _quantity(event["transactionIndex"]) != tx_index
            or event["removed"] is not False
        ):
            raise ValueError("Receipt event is not bound to its transaction and block")
    data = transaction["input"].lower()
    method_key = (chain_id, target, data[:10])
    action, title, method = _METHODS.get(method_key, ("contract_call", "链上合约调用", data[:10] or "0x"))
    status = _quantity(receipt["status"])
    if status not in (0, 1):
        raise ValueError("Malformed receipt status")
    summary = "原始收据显示该交易已打包；具体业务结果以原样本核验范围为准。"
    if status == 0:
        verdict = Verdict.FAIL
        summary = "原始收据显示交易回滚，本笔交易未完成所声明的状态变更。"
    elif action == "wrap":
        amount = _quantity(transaction["value"])
        deposits = [event for event in receipt["logs"] if (
            _hex(event["address"], 40) == target and len(event.get("topics", [])) == 2
            and event["topics"][0].lower() == DEPOSIT
            and _address(int(_hex(event["topics"][1], 64), 16)) == sender
        )]
        if len(deposits) != 1 or _words(deposits[0]["data"], 1)[0] != amount:
            raise ValueError("Deposit event does not match the executor's native input")
        summary = f"执行账户支付 BNB {_units(amount, 18)}；WBNB 合约的 Deposit 事件记录同账户获得 WBNB {_units(amount, 18)}。"
    elif action == "swap":
        values = _words("0x" + data[10:], 8)
        token_in, token_out, recipient = _address(values[0]), _address(values[1]), _address(values[3])
        transfers = _transfers(receipt)
        amount_in = sum(amount for token, source, _, amount in transfers if token == token_in and source == sender)
        amount_out = sum(amount for token, _, destination, amount in transfers if token == token_out and destination == recipient)
        if amount_in <= 0 or amount_out <= 0:
            raise ValueError("Swap asset transfers are missing from the retained receipt")
        summary = (
            f"收据中的资产转移记录实际支付 {_asset(chain_id, token_in, amount_in)}，"
            f"接收账户 {recipient} 实收 {_asset(chain_id, token_out, amount_out)}；"
            f"调用中最低接收量为 {_asset(chain_id, token_out, values[6])}。"
        )
    elif action == "increase_liquidity":
        token_id = _words("0x" + data[10:], 6)[0]
        events = [event for event in receipt["logs"] if (
            _hex(event["address"], 40) == target and len(event.get("topics", [])) == 2
            and event["topics"][0].lower() == INCREASE_TOPIC
            and int(_hex(event["topics"][1], 64), 16) == token_id
        )]
        if len(events) != 1:
            raise ValueError("IncreaseLiquidity event for the called position is missing or ambiguous")
        liquidity, amount0, amount1 = _words(events[0]["data"], 3)
        outgoing = [f"{_asset(chain_id, token, amount)} → {destination}"
                    for token, source, destination, amount in _transfers(receipt) if source == sender]
        summary = (
            f"仓位 #{token_id} 的 IncreaseLiquidity 事件记录流动性增加 {liquidity}（协议单位），"
            f"amount0={amount0}、amount1={amount1}（资产最小单位）。"
            + ("执行账户的实际资产转出：" + "；".join(outgoing) + "。" if outgoing else "")
        )
    return ChainAction(
        sample_id=sample_id, chain_id=chain_id, action=action, title=title,
        transaction_hash=tx_hash, block_number=block_number, executor=sender,
        target=target, method=method, summary=summary, verdict=verdict, evidence=evidence,
    )
