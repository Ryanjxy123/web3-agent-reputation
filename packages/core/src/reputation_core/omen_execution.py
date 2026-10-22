"""Verify Olas/Safe/Omen execution from supplied facts, with no I/O or scoring."""

from dataclasses import dataclass
import re

from eth_hash.auto import keccak

from reputation_core.admission import Verdict
from reputation_core.reporting import ReportFinding

SERVICE_REGISTRY = "0x9338b5153ae39bb89f50468e608ed9d764b755fd"
MULTISEND = "0xa238cbeb142c10ef7ad8442c6d1f9e89e07e7761"
WXDAI = "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d"
CONDITIONAL_TOKENS = "0xceafdd6bc0bef976fdcd1112955828e00543c0ce"


def topic(signature: str) -> str:
    return "0x" + keccak(signature.encode("ascii")).hex()


SAFE_SUCCESS = topic("ExecutionSuccess(bytes32,uint256)")
SAFE_FAILURE = topic("ExecutionFailure(bytes32,uint256)")
BUY = topic("FPMMBuy(address,uint256,uint256,uint256,uint256)")
TRANSFER = topic("Transfer(address,address,uint256)")
TRANSFER_SINGLE = topic("TransferSingle(address,address,address,uint256,uint256)")


class EvidenceMismatch(ValueError):
    """A complete observation contradicts an asserted binding or constraint."""


def same(actual, expected, label: str) -> None:
    if actual != expected:
        raise EvidenceMismatch(label)


def hex_value(value, digits: int | None = None) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise ValueError("缺少规范十六进制证据")
    if digits is not None and len(value) != digits + 2:
        raise ValueError("十六进制证据长度错误")
    return value.lower()


def words(value: str) -> list[int]:
    data = hex_value(value)[2:]
    if len(data) % 64:
        raise ValueError("ABI字对齐错误")
    return [int(data[i:i + 64], 16) for i in range(0, len(data), 64)]


def address(value: int) -> str:
    if not 0 < value < 2**160:
        raise ValueError("ABI地址不规范")
    return f"0x{value:040x}"


def address_array(value: str, *, tuple_offset: int = 0) -> list[str]:
    data = words(value)
    offset = data[tuple_offset]
    if offset % 32:
        raise ValueError("ABI数组偏移不规范")
    start = offset // 32
    count = data[start]
    if start + 1 + count != len(data):
        raise ValueError("ABI数组长度不完整")
    return [address(item) for item in data[start + 1:]]


def dynamic(data: bytes, offset: int) -> bytes:
    if offset % 32 or offset + 32 > len(data):
        raise ValueError("动态参数偏移错误")
    length = int.from_bytes(data[offset:offset + 32], "big")
    if offset + 32 + length > len(data):
        raise ValueError("动态参数截断")
    return data[offset + 32:offset + 32 + length]


def safe_calls(calldata: str) -> tuple[list[tuple[str, bytes]], bytes]:
    if calldata[:10].lower() != "0x6a761202":
        raise ValueError("尚未适配该Safe入口")
    data = bytes.fromhex(calldata[10:])
    if len(data) < 320:
        raise ValueError("Safe参数截断")
    static = [int.from_bytes(data[i:i + 32], "big") for i in range(0, 320, 32)]
    payload, signatures = dynamic(data, static[2]), dynamic(data, static[9])
    destination, operation = address(static[0]), static[3]
    same(static[1], 0, "已审阅买入不应附带原生币value")
    if operation == 0:
        return [(destination, payload)], signatures
    if operation != 1 or destination != MULTISEND or payload[:4].hex() != "8d80ff0a":
        raise ValueError("该Safe调用组合尚未适配")
    packed = dynamic(payload[4:], int.from_bytes(payload[4:36], "big"))
    result, cursor = [], 0
    while cursor < len(packed):
        if cursor + 85 > len(packed):
            raise ValueError("MultiSend操作头截断")
        if packed[cursor] != 0:
            raise ValueError("内层delegatecall尚未适配")
        target = address(int.from_bytes(packed[cursor + 1:cursor + 21], "big"))
        same(int.from_bytes(packed[cursor + 21:cursor + 53], "big"), 0, "内层原生币value不为0")
        length = int.from_bytes(packed[cursor + 53:cursor + 85], "big")
        cursor += 85
        if cursor + length > len(packed):
            raise ValueError("MultiSend调用数据截断")
        result.append((target, packed[cursor:cursor + length]))
        cursor += length
    return result, signatures


def units(value: int) -> str:
    whole, fraction = divmod(value, 10**18)
    tail = f"{fraction:018d}".rstrip("0")
    return str(whole) + ("." + tail if tail else "")


@dataclass(frozen=True)
class OmenExecutionVerification:
    verdict: Verdict
    checks: list[ReportFinding]
    facts: dict


def verify_omen_execution(proof: dict, *, safe: str, service_id: int, trade: dict,
                          confirmation_head: int) -> OmenExecutionVerification:
    """Check one observed buy. Does not infer population failure rate or a score."""
    findings, facts = [], {}

    def passed(label: str, explanation: str) -> None:
        findings.append(ReportFinding(label=label, verdict=Verdict.PASS, explanation=explanation))

    try:
        safe = hex_value(safe, 40)
        tx, receipt, block = proof["transaction"], proof["receipt"], proof["block"]
        tx_hash = hex_value(tx["hash"], 64)
        height = int(hex_value(tx["blockNumber"]), 16)
        same(int(hex_value(tx["chainId"]), 16), 100, "交易链不是Gnosis")
        same(hex_value(tx["to"], 40), safe, "实际调用目标不是该Safe")
        same(hex_value(trade["creator"]["id"], 40), safe, "索引交易者与Safe不符")
        same(hex_value(trade["transactionHash"], 64), tx_hash, "索引与RPC交易哈希不符")
        block_hash = hex_value(tx["blockHash"], 64)
        index = int(hex_value(tx["transactionIndex"]), 16)
        for key, expected in (("transactionHash", tx_hash), ("blockHash", block_hash),
                              ("blockNumber", tx["blockNumber"]), ("transactionIndex", tx["transactionIndex"]),
                              ("from", tx["from"]), ("to", safe)):
            same(receipt[key].lower(), expected.lower(), "回执绑定错误：" + key)
        same(hex_value(block["hash"], 64), block_hash, "区块哈希不符")
        same(int(hex_value(block["number"]), 16), height, "区块高度不符")
        same(block["transactions"][index].lower(), tx_hash, "交易不在给定区块位置")
        same(int(hex_value(receipt["status"]), 16), 1, "真实交易回滚")
        if confirmation_head - height < 64:
            raise ValueError("独立确认高度不足64块")
        facts.update(transaction_hash=tx_hash, block_number=height, safe=safe,
                     submitter=hex_value(tx["from"], 40), timestamp=int(block["timestamp"], 16))
        passed("交易、回执与区块绑定", f"Gnosis区块{height}的第{index}笔交易与回执/区块哈希一致，已有至少64块确认。")

        registered = words(proof["service_before"])
        same(address(registered[1]), safe, "交易前注册服务没有绑定该Safe")
        same(registered[6], 4, "交易前服务不在Deployed状态")
        instances = address_array(proof["agent_instances_before"], tuple_offset=1)
        owners = address_array(proof["safe_owners_before"])
        threshold = words(proof["safe_threshold_before"])[0]
        proxy_hash = "0x" + keccak(bytes.fromhex(hex_value(proof["safe_code"])[2:])).hex()
        if proxy_hash != "0xb89c1b3bdf2cf8827818646bce9a8f6e372885f8c55e5c07acbd307cb133b000":
            raise ValueError("该账户运行时代码不是已审阅的官方Safe v1.3.0代理")
        # This reviewed first cohort uses a single registered instance and 1/1 Safe.
        if len(owners) != 1 or threshold != 1 or len(instances) != 1:
            raise ValueError("该多签阈值/实例结构尚未审阅，保留缺项")
        same(owners[0], instances[0], "历史Safe owner与注册执行实例不一致")
        if facts['submitter'] != instances[0]:
            raise ValueError('本笔由中继者提交，尚缺内层签名者的独立归属证明，不能直接归给注册实例。')
        passed("历史注册与执行授权", f"交易前一区块的Olas服务#{service_id}绑定此Safe；唯一注册实例也是当时1/1 Safe owner。")

        singleton = address(words(proof["safe_master_copy_before"])[0])
        if singleton != "0xd9db270c1b5e3bd161e8c8503c55ceabee709552":
            raise ValueError("该Safe实现版本尚未审阅")
        code_hash = "0x" + keccak(bytes.fromhex(hex_value(proof["singleton_code_before"])[2:])).hex()
        same(code_hash, "0xbba688fbdb21ad2bb58bc320638b43d94e7d100f6f3ebaab0a4e4de6304b1c2e", "历史Safe实现字节码与官方部署不符")
        passed("智能账户实现", "历史masterCopy与Safe官方v1.3.0部署地址一致，实现字节码Keccak与官方codeHash一致。")

        logs = receipt["logs"]
        for log in logs:
            for key, expected in (("transactionHash", tx_hash), ("blockHash", block_hash),
                                  ("blockNumber", tx["blockNumber"]), ("transactionIndex", tx["transactionIndex"])):
                same(log[key].lower(), expected.lower(), "事件归属错误：" + key)
            same(log["removed"], False, "事件已被重组移除")
        execution = [log for log in logs if log["address"].lower() == safe
                     and log["topics"][0].lower() in (SAFE_SUCCESS, SAFE_FAILURE)]
        if len(execution) != 1:
            raise ValueError("尚缺唯一可识别Safe内层结果事件")
        same(execution[0]["topics"][0].lower(), SAFE_SUCCESS, "Safe内层执行失败")
        calls, signatures = safe_calls(tx["input"])
        if len(signatures) != 65 or signatures[64] not in (27, 28, 31, 32):
            raise ValueError("该签名结构尚未审阅")
        safe_hash = hex_value(execution[0]["data"])[2:66]
        facts["safe_transaction_hash"] = "0x" + safe_hash
        passed("签名与Safe内层结果", "真实交易携带一份ECDSA签名，Safe在执行时验签并发出ExecutionSuccess；平台未持有私钥，也未把外层status=1单独当业务完成。")

        market = hex_value(trade["fpmm"]["id"], 40)
        buy_selector = keccak(b"buy(uint256,uint256,uint256)")[:4]
        buy_calls = [payload for target, payload in calls if target == market and payload[:4] == buy_selector]
        if len(buy_calls) != 1:
            raise ValueError("已签调用中的业务组合尚不能归入唯一目标buy")
        arguments = words("0x" + buy_calls[0][4:].hex())
        same(len(arguments), 3, "买入参数长度错误")
        investment, outcome, minimum = arguments
        approvals = [payload for target, payload in calls if target == WXDAI and payload[:4].hex() == "095ea7b3"]
        if len(approvals) == 1 and len(calls) == 2:
            approval = words("0x" + approvals[0][4:].hex())
            same(approval, [int(market, 16), investment], "spender或授权额度与本次买入不符")
            authorization = f"同笔仅授权本市场花费{units(investment)} wxDAI"
        elif not approvals and len(calls) == 1:
            allowance = words(proof['collateral_allowance_before'])[0]
            if allowance < investment:
                raise ValueError("前一区块额度不足，需要同区块授权变更证据，尚不能判断")
            authorization = f"复用前一区块已有授权额度{units(allowance)} wxDAI，本笔未新建授权"
        else:
            raise ValueError("该授权/买入调用组合尚未适配")
        same(address(words(proof["market_collateral"])[0]), WXDAI, "真实市场抵押资产不是wxDAI")
        same(address(words(proof["market_conditional_tokens"])[0]), CONDITIONAL_TOKENS, "市场条件代币合约不符")
        condition = hex_value(proof["market_condition"], 64)
        buys = [log for log in logs if log["address"].lower() == market and log["topics"][0].lower() == BUY]
        same(len(buys), 1, "缺少唯一目标合约FPMMBuy事件")
        buy = buys[0]
        same(address(int(buy["topics"][1], 16)), safe, "FPMMBuy实际buyer不是Safe")
        same(int(buy["topics"][2], 16), outcome, "买入结果方向不符")
        invested, fee, tokens = words(buy["data"])
        same(invested, investment, "实际投入与已签参数不符")
        if tokens < minimum:
            raise EvidenceMismatch("实收头寸少于已签minimum")
        same(investment, int(trade["collateralAmount"]), "独立索引投入金额与链上不符")
        same(tokens, int(trade["outcomeTokensTraded"]), "独立索引头寸数量与链上不符")
        same(outcome, int(trade["outcomeIndex"]), "独立索引结果方向与链上不符")
        passed("已签授权与业务参数", f"{authorization}；buy选择outcome {outcome}，最低接收{units(minimum)}份头寸；真实事件与之匹配。")

        spent = [log for log in logs if log["address"].lower() == WXDAI and log["topics"][0].lower() == TRANSFER
                 and len(log["topics"]) == 3 and int(log["topics"][1], 16) == int(safe, 16)
                 and int(log["topics"][2], 16) == int(market, 16)]
        same(len(spent), 1, "缺少Safe实际抵押资产转出")
        same(words(spent[0]["data"])[0], investment, "抵押资产实际转出金额不符")
        positions = [log for log in logs if log["address"].lower() == CONDITIONAL_TOKENS
                     and log["topics"][0].lower() == TRANSFER_SINGLE and len(log["topics"]) == 4
                     and int(log["topics"][2], 16) == int(market, 16)
                     and int(log["topics"][3], 16) == int(safe, 16)]
        matching = [log for log in positions if words(log["data"])[1] == tokens]
        same(len(matching), 1, "缺少相同数量的真实条件头寸到账")
        position_id = words(matching[0]["data"])[0]
        expected_position = words(proof['position_id_before'])[0]
        same(position_id, expected_position, "到账头寸ID与条件/方向/抵押资产独立计算不符")
        passed("实际资产变化与头寸到账", f"Safe实际支出{units(investment)} wxDAI，收到{units(tokens)}份条件头寸，费用{units(fee)} wxDAI。")
        facts.update(market=market, investment=units(investment), fee=units(fee), tokens=units(tokens), authorization=authorization,
                     minimum_tokens=units(minimum), outcome=outcome, position_id=str(position_id), condition_id=condition,
                     execution_path=('Safe.execTransaction → MultiSend' if words('0x' + tx['input'][10:])[3] == 1
                                     else 'Safe.execTransaction') + (' → approve → buy' if approvals else ' → buy（沿用已有授权）'))
        return OmenExecutionVerification(Verdict.PASS, findings, facts)
    except EvidenceMismatch as error:
        findings.append(ReportFinding(label="链上事实或约束矛盾", verdict=Verdict.FAIL, explanation=str(error)))
        return OmenExecutionVerification(Verdict.FAIL, findings, facts)
    except (ValueError, KeyError, IndexError, TypeError) as error:
        missing = {'safe_threshold_before': '尚未取得交易前历史区块的Safe签名阈值，当前不能完成授权核验。',
                   'safe_code': '尚未取得样本区块的账户运行时代码，当前不能确认其使用已审阅的Safe代理。'}
        explanation = missing.get(error.args[0], '必要的独立原件尚未取得，当前无法判断。') if isinstance(error, KeyError) else str(error)
        findings.append(ReportFinding(label="尚缺可判定证据", verdict=Verdict.UNKNOWN, explanation=explanation))
        return OmenExecutionVerification(Verdict.UNKNOWN, findings, facts)
