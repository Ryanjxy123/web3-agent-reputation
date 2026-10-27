"""Pure checks for exact-input ERC20 swap plans and their real execution.

Inputs are authenticated by the platform source verifier. No Agent identity,
particular wallet, network access, clock or database belongs in these rules.
"""
from dataclasses import dataclass, field
import re

from eth_hash.auto import keccak

from reputation_core.admission import Verdict
from reputation_core.prediction_chain import calldata, selector
from reputation_core.reporting import ReportFinding

APPROVAL_TOPIC = "0x" + keccak(b"Approval(address,address,uint256)").hex()
TRANSFER_TOPIC = "0x" + keccak(b"Transfer(address,address,uint256)").hex()
SWAP_TOPIC = "0x" + keccak(b"Swap(address,address,int256,int256,uint160,uint128,int24)").hex()
SWAP_METHOD = "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))"


@dataclass(frozen=True)
class SwapRequest:
    chain_id: int
    token_in: str
    token_out: str
    amount_in: int
    recipient: str
    executor: str
    router: str
    factory: str
    slippage_bps: int
    input_decimals: int
    output_decimals: int
    expected_account_code: str | None = None


@dataclass
class SwapVerification:
    verdict: Verdict
    reason: str
    checks: list[ReportFinding] = field(default_factory=list)
    facts: dict = field(default_factory=dict)


class Contradiction(ValueError):
    pass


def require(value, message):
    if not value:
        raise Contradiction(message)


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ValueError("Missing or malformed address")
    return value.lower()


def integer(value):
    if type(value) is int:
        return value
    if not isinstance(value, str) or not re.fullmatch(r'(?:0x[0-9a-fA-F]+|-?[0-9]+)', value):
        raise ValueError("Expected an exact integer amount")
    return int(value, 16) if value.startswith("0x") else int(value)


def hex_bytes(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", value):
        raise ValueError("Missing or malformed ABI bytes")
    return bytes.fromhex(value[2:])


def words(value, count):
    raw = hex_bytes(value)
    if len(raw) != count * 32:
        raise ValueError("Unsupported ABI word count")
    return [int.from_bytes(raw[index:index + 32], "big") for index in range(0, len(raw), 32)]


def finding(label, verdict, explanation):
    return ReportFinding(label=label, verdict=verdict, explanation=explanation)


def encode_batch(calls):
    def word(value):
        return value.to_bytes(32, "big")
    tuples = []
    for call in calls:
        raw = hex_bytes(call["data"])
        tuples.append(bytes.fromhex(address(call["target"])[2:]).rjust(32, b"\0")
                      + word(integer(call["value"])) + word(96) + word(len(raw))
                      + raw + bytes((-len(raw)) % 32))
    offset, offsets = len(tuples) * 32, []
    for item in tuples:
        offsets.append(word(offset)); offset += len(item)
    return selector("executeBatch((address,uint256,bytes)[])") + (
        word(32) + word(len(tuples)) + b"".join(offsets) + b"".join(tuples)).hex()


def decode_batch_results(value):
    raw = hex_bytes(value)
    def at(index):
        if index < 0 or index + 32 > len(raw):
            raise ValueError("Incomplete batch return")
        return int.from_bytes(raw[index:index + 32], "big")
    if at(0) != 32 or at(32) != 2:
        raise ValueError("Expected two batch return values")
    values = []
    for index in range(2):
        offset = at(64 + index * 32)
        if offset % 32 or offset < 64:
            raise ValueError("Malformed batch return offset")
        start = 64 + offset
        size = at(start)
        if start + 32 + size > len(raw):
            raise ValueError("Incomplete batch return payload")
        values.append("0x" + raw[start + 32:start + 32 + size].hex())
    return values


def decode_batch(value):
    """Decode the canonical executeBatch envelope without guessing its actor."""
    raw = hex_bytes(value)
    if raw[:4].hex() != selector('executeBatch((address,uint256,bytes)[])')[2:]:
        raise ValueError('Unsupported batch selector')
    body = raw[4:]
    def at(index):
        if index < 0 or index + 32 > len(body):
            raise ValueError('Incomplete batch call')
        return int.from_bytes(body[index:index + 32], 'big')
    if at(0) != 32 or not 1 <= at(32) <= 64:
        raise ValueError('Unsupported batch array')
    calls = []
    for index in range(at(32)):
        offset = at(64 + index * 32)
        start = 64 + offset
        target, amount, data_offset = at(start), at(start + 32), at(start + 64)
        if target >= 2**160 or data_offset != 96:
            raise ValueError('Malformed batch tuple')
        size = at(start + data_offset)
        begin = start + data_offset + 32
        if begin + size > len(body):
            raise ValueError('Incomplete inner calldata')
        calls.append({'target': f'0x{target:040x}', 'value': str(amount),
                      'data': '0x' + body[begin:begin + size].hex()})
    if encode_batch(calls) != value.lower():
        raise ValueError('Noncanonical batch encoding')
    return calls


def plan_facts(request: SwapRequest, builder: dict):
    """Validate the business plan; format alone is not a functional PASS."""
    if (request.chain_id <= 0 or request.amount_in <= 0 or not 0 <= request.slippage_bps < 10000
        or not 0 <= request.input_decimals <= 255 or not 0 <= request.output_decimals <= 255
        or address(request.token_in) == address(request.token_out)):
        raise ValueError('冻结请求不属于有效的精确输入兑换，不能归责提供方')
    require(builder.get("status") == "ready", "服务未返回约定的可用兑换方案")
    quote, execution = builder["quote"], builder["execution"]
    transactions = builder["transactions"]
    require(set(transactions) == {"approval", "swap"}, "方案包含未约定的额外交易或缺少完整操作")
    approval, swap = transactions["approval"], transactions["swap"]
    require(integer(approval["chainId"]) == integer(swap["chainId"]) == request.chain_id,
            "方案交易链号与请求不一致")
    if address(swap['to']) != address(request.router):
        if address(execution.get('router')) == address(request.router):
            raise Contradiction('方案宣称的Router与真实交易目标不一致')
        raise ValueError('提供方返回了尚未适配的路由，不能直接判Agent失败')
    require(address(approval["to"]) == address(request.token_in)
            and integer(approval.get("value", 0)) == integer(swap.get("value", 0)) == 0,
            "授权或兑换目标、原生币转出与请求不一致")
    require(approval["data"].lower() == calldata("approve(address,uint256)", request.router, request.amount_in),
            "授权不是给本任务Router的精确输入额度")
    swap_data = hex_bytes(swap["data"])
    if swap_data[:4].hex() != selector(SWAP_METHOD)[2:]:
        raise ValueError('尚未适配这项兑换方法，不能仅凭选择器不同归责Agent')
    token_in, token_out, tier, recipient, amount, minimum, sqrt_limit = words("0x" + swap_data[4:].hex(), 7)
    require(token_in == int(request.token_in, 16) and token_out == int(request.token_out, 16)
            and recipient == int(request.recipient, 16) and amount == request.amount_in,
            "实际calldata的资产、收款人或输入金额与请求不一致")
    if tier not in (100, 500, 3000, 10000) or sqrt_limit != 0:
        raise ValueError('该费率或额外价格限制尚不在本版本核验范围')
    require(minimum > 0, '最低到账量无效')
    require(address(quote["tokenIn"]["address"]) == address(request.token_in)
            and address(quote["tokenOut"]["address"]) == address(request.token_out)
            and integer(quote["tokenIn"]["amountRaw"]) == request.amount_in
            and integer(quote["tokenIn"]["decimals"]) == request.input_decimals
            and integer(quote["tokenOut"]["decimals"]) == request.output_decimals,
            "展示资产、整数单位或decimals与请求和可信资料不一致")
    estimate = integer(quote["tokenOut"]["estimatedAmountRaw"])
    require(integer(quote["slippageBps"]) == request.slippage_bps
            and integer(quote["feeTier"]) == tier
            and integer(quote["tokenOut"]["minimumAmountRaw"]) == minimum
            and minimum == estimate * (10000 - request.slippage_bps) // 10000,
            "最低到账、滑点或报价与实际兑换约束不一致")
    require(integer(execution["chainId"]) == request.chain_id
            and address(execution["recipient"]) == address(request.recipient)
            and address(execution["router"]) == address(request.router),
            "执行元数据与实际任务身份不一致")
    calls = [{"target": approval["to"], "value": "0", "data": approval["data"]},
             {"target": swap["to"], "value": "0", "data": swap["data"]}]
    return {"amount_in_raw": str(amount), "minimum_out_raw": str(minimum), "estimated_out_raw": str(estimate),
            "fee_tier": tier, "deadline": integer(execution["deadline"]), "calls": calls,
            "batch_data": encode_batch(calls), "input_symbol": quote["tokenIn"].get("symbol"),
            "output_symbol": quote["tokenOut"].get("symbol")}


def verify_swap_function(request: SwapRequest, builder: dict, simulation: dict | None) -> SwapVerification:
    facts = {}
    try:
        facts = plan_facts(request, builder)
        if simulation is None:
            raise ValueError("尚无可信固定区块的完整方案模拟")
        call = simulation["call"]
        require(integer(simulation["chain_id"]) == request.chain_id
                and address(call["from"]) == address(request.executor)
                and address(call["to"]) == address(request.executor)
                and integer(call.get("value", 0)) == 0
                and call["data"].lower() == facts["batch_data"], "独立模拟没有使用同一账户和完整方案")
        if simulation.get("error") is not None:
            raise ValueError("模拟回滚或节点报错，尚不能独立归责")
        if request.expected_account_code is None or (simulation.get('account_code') or '').lower() != request.expected_account_code.lower():
            raise ValueError('尚未从同块代码证明受支持的智能账户执行模型')
        returned = decode_batch_results(simulation["result"])
        actual = words(returned[1], 1)[0]
        require(actual >= int(facts["minimum_out_raw"]), "独立模拟实际输出低于已声明最低量")
        facts.update(simulated_out_raw=str(actual), block_number=integer(simulation["block_number"]))
        return SwapVerification(Verdict.PASS, "方案真实参数、精确授权、最低到账及独立完整模拟一致。", [
            finding("输入、目标与精确授权", Verdict.PASS, "实际calldata按冻结请求核验，不仅检查JSON格式。"),
            finding("独立固定块模拟", Verdict.PASS, f"模拟输出{actual}单位，最低要求{facts['minimum_out_raw']}单位。"),
        ], facts)
    except Contradiction as exc:
        return SwapVerification(Verdict.FAIL, str(exc), [finding("功能约束矛盾", Verdict.FAIL, str(exc))], facts)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return SwapVerification(Verdict.UNKNOWN, str(exc), [finding("功能证据缺项", Verdict.UNKNOWN, str(exc))], facts)


def verify_swap_execution(request: SwapRequest, builder: dict, proof: dict | None,
                          confirmation_distance: int = 64) -> SwapVerification:
    facts = {}
    try:
        facts = plan_facts(request, builder)
        if proof is None:
            raise ValueError("尚无这项任务的独立交易与回执证据")
        tx, receipt, block = proof["transaction"], proof["receipt"], proof["block"]
        tx_hash = proof["expected_transaction_hash"].lower()
        require(tx["hash"].lower() == receipt["transactionHash"].lower() == tx_hash,
                "交易哈希与冻结发送意图不一致")
        require(integer(tx["chainId"]) == request.chain_id
                and address(tx["from"]) == address(request.executor)
                and address(tx["to"]) == address(request.executor)
                and integer(tx["value"]) == 0 and tx["input"].lower() == facts["batch_data"],
                "真实交易没有执行该任务的完整授权兑换方案")
        number = integer(receipt["blockNumber"])
        require(tx["blockHash"].lower() == receipt["blockHash"].lower() == block["hash"].lower()
                and integer(tx["blockNumber"]) == integer(block["number"]) == number
                and integer(tx["transactionIndex"]) == integer(receipt["transactionIndex"])
                and tx_hash in [value.lower() for value in block["transactions"]], "交易不在对应canonical区块")
        if integer(proof["head"]) - number < confirmation_distance:
            raise ValueError("确认距离尚不足，保留任务等待证据")
        if integer(receipt["status"]) != 1:
            raise ValueError("交易回滚；现有证据尚不能将市场或操作者原因归责提供方")
        pool = address(proof["pool"])
        if int(pool, 16) == 0:
            raise ValueError("官方Factory尚未证明本任务对应池")
        logs = receipt["logs"]
        for log in logs:
            require(log["transactionHash"].lower() == tx_hash and log["blockHash"].lower() == block["hash"].lower()
                    and not log.get("removed", False), "日志包含不属于本笔canonical交易的内容")
        def topic(value):
            return "0x" + address(value)[2:].rjust(64, "0")
        def transferred(token, sender, recipient):
            return [integer(log["data"]) for log in logs if address(log["address"]) == address(token)
                    and [v.lower() for v in log["topics"]] == [TRANSFER_TOPIC, topic(sender), topic(recipient)]]
        paid, received = transferred(request.token_in, request.executor, pool), transferred(request.token_out, pool, request.recipient)
        outgoing = [log for log in logs if address(log["address"]) == address(request.token_in)
                    and len(log["topics"]) == 3 and log["topics"][0].lower() == TRANSFER_TOPIC
                    and log["topics"][1].lower() == topic(request.executor)]
        require(paid == [request.amount_in] and sum(integer(log["data"]) for log in outgoing) == request.amount_in,
                "真实输入资产转出金额或去向与任务不一致")
        require(bool(received) and sum(received) >= int(facts["minimum_out_raw"]), "真实到账低于最低量或收款人不符")
        swaps = [log for log in logs if address(log["address"]) == pool
                 and [v.lower() for v in log["topics"]] == [SWAP_TOPIC, topic(request.router), topic(request.recipient)]]
        require(len(swaps) == 1, "缺少唯一对应官方池Swap事件")
        raw = hex_bytes(swaps[0]["data"])
        if len(raw) != 160:
            raise ValueError("官方池Swap事件格式不完整")
        amount0, amount1 = int.from_bytes(raw[:32], "big", signed=True), int.from_bytes(raw[32:64], "big", signed=True)
        input_amount, output_amount = ((amount0, amount1) if int(request.token_in, 16) < int(request.token_out, 16)
                                       else (amount1, amount0))
        require(input_amount == request.amount_in and output_amount == -sum(received), "池Swap与实际ERC20转账不一致")
        approvals = [integer(log["data"]) for log in logs if address(log["address"]) == address(request.token_in)
                     and [v.lower() for v in log["topics"]] == [APPROVAL_TOPIC, topic(request.executor), topic(request.router)]]
        require(approvals.count(request.amount_in) == 1 and all(v in (0, request.amount_in) for v in approvals),
                "真实授权额度与精确输入不符")
        require(integer(proof["allowance_after"]) == 0, "任务完成后Router仍有本次未用完授权")
        if request.expected_account_code is None or proof['account_code_before'].lower() != request.expected_account_code.lower():
            raise ValueError('尚未核实本次交易使用的智能账户实现')
        require(proof["account_code_before"].lower() == proof["account_code_after"].lower(), "本次执行改变账户委托")
        facts.update(transaction_hash=tx_hash, block_number=number, pool=pool,
                     actual_out_raw=str(sum(received)), confirmation_distance=integer(proof["head"]) - number)
        return SwapVerification(Verdict.PASS, "真实完整兑换、官方池事件、资产到账与授权约束一致。", [
            finding("任务与真实执行", Verdict.PASS, "提供方构造、操作者签名、同一链上账户执行，角色分别核实。"),
            finding("真实资产和授权", Verdict.PASS, f"输入{request.amount_in}单位，实际到账{sum(received)}单位，剩余额度0。"),
        ], facts)
    except Contradiction as exc:
        return SwapVerification(Verdict.FAIL, str(exc), [finding("交易约束矛盾", Verdict.FAIL, str(exc))], facts)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return SwapVerification(Verdict.UNKNOWN, str(exc), [finding("交易证据缺项", Verdict.UNKNOWN, str(exc))], facts)
