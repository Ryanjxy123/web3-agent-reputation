"""Pure ERC20 transfer-record verification; RPC provenance is checked by the caller."""

import re

from reputation_core import Verdict
from reputation_core.behavior import TRANSFER


def _hex(value: object, digits: int) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{" + str(digits) + "}", value):
        raise ValueError('缺少或格式错误的十六进制证据。')
    return value.lower()


def _quantity(value: object) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,63})", value):
        raise ValueError('RPC数量缺失或不是规范的无符号十六进制数。')
    return int(value, 16)


def _same(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(label + '不一致，不能作为确定性业务判据。')


def verify_transfer_record(claimed_amount: int, tx_hash: str, chain_id: int, token: str,
                           recipients: tuple[str, ...], values: dict) -> tuple[Verdict, str, dict]:
    """Compare a displayed integer with all matching ERC20 transfers, rounded half up.

    Values are the six RPC results, already authenticated and scoped by the caller.
    This proves a transfer amount, not the Agent's ownership or execution of it.
    """
    try:
        if type(claimed_amount) is not int or claimed_amount < 0 or type(chain_id) is not int or chain_id <= 0:
            raise ValueError('声明金额或目标链号无效。')
        expected_hash, token = _hex(tx_hash, 64), _hex(token, 40)
        if not isinstance(recipients, tuple) or not recipients:
            raise ValueError('缺少预先确定的接收地址集合。')
        destinations = {_hex(address, 40) for address in recipients}
        if len(destinations) != len(recipients):
            raise ValueError('接收地址集合含有重复项。')
        _same(_quantity(values['chain']), chain_id, 'RPC链号')
        head = _quantity(values['head'])
        tx, receipt, header = values['transaction'], values['receipt'], values['header']
        _same(_hex(tx['hash'], 64), expected_hash, '交易哈希')
        _same(_hex(receipt['transactionHash'], 64), expected_hash, '回执交易哈希')
        _same(_quantity(tx['chainId']), chain_id, '交易链号')
        block, index = _quantity(tx['blockNumber']), _quantity(tx['transactionIndex'])
        block_hash = _hex(tx['blockHash'], 64)
        for record, number_key, hash_key in ((receipt, 'blockNumber', 'blockHash'), (header, 'number', 'hash')):
            _same(_quantity(record[number_key]), block, '区块高度')
            _same(_hex(record[hash_key], 64), block_hash, '区块哈希')
        _same(_quantity(receipt['transactionIndex']), index, '回执交易序号')
        transactions = header['transactions']
        if not isinstance(transactions, list):
            raise ValueError('区块缺少交易哈希列表。')
        hashes = [_hex(item, 64) for item in transactions]
        if len(set(hashes)) != len(hashes) or index >= len(hashes):
            raise ValueError('区块交易列表重复或缺少本交易序号。')
        _same(hashes[index], expected_hash, '区块中的交易位置')
        _same(_hex(receipt['from'], 40), _hex(tx['from'], 40), '回执发送地址')
        to = tx['to']
        _same(None if receipt['to'] is None else _hex(receipt['to'], 40),
              None if to is None else _hex(to, 40), '回执目标地址')
        if head - block < 64:
            raise ValueError('独立链头与交易区块距离不足64块。')
        status = _quantity(receipt['status'])
        if status not in (0, 1):
            raise ValueError('回执状态不是0或1。')
        decimals = int(_hex(values['decimals'], 64), 16)
        if decimals > 255:
            raise ValueError('ERC20 decimals超出uint8范围。')
        logs = receipt['logs']
        if not isinstance(logs, list):
            raise ValueError('回执缺少完整日志列表。')
        seen, matched, amount = set(), [], 0
        for log in logs:
            address = _hex(log['address'], 40)
            _same(_hex(log['transactionHash'], 64), expected_hash, '日志交易哈希')
            _same(_hex(log['blockHash'], 64), block_hash, '日志区块哈希')
            _same(_quantity(log['blockNumber']), block, '日志区块高度')
            _same(_quantity(log['transactionIndex']), index, '日志交易序号')
            if log['removed'] is not False:
                raise ValueError('日志被移除或缺少明确的removed=false。')
            log_index = _quantity(log['logIndex'])
            if log_index in seen:
                raise ValueError('回执含有重复日志序号。')
            seen.add(log_index)
            topics, data = log['topics'], log['data']
            if not isinstance(topics, list) or len(topics) > 4:
                raise ValueError('事件topics不是有效列表。')
            topics = [_hex(topic, 64) for topic in topics]
            if not isinstance(data, str) or not re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*', data):
                raise ValueError('事件data不是规范字节串。')
            if address == token and topics and topics[0] == TRANSFER:
                if len(topics) != 3 or any(int(topic, 16) >= 2**160 for topic in topics[1:]):
                    raise ValueError('目标ERC20 Transfer的topics或地址填充错误。')
                raw_amount = int(_hex(data, 64), 16)
                if '0x' + topics[2][-40:] in destinations:
                    matched.append(log_index)
                    amount += raw_amount
        for record in (receipt, header, *logs):
            if 'chainId' in record:
                _same(_quantity(record['chainId']), chain_id, '证据链号')
        if status == 0 and logs:
            raise ValueError('回滚回执却包含已执行日志，来源矛盾。')
        scale = 10**decimals
        displayed = (2 * amount + scale) // (2 * scale)
        detail = {'chain_id': chain_id, 'transaction_hash': expected_hash, 'token': token,
                  'recipients': sorted(destinations), 'block_number': block, 'block_hash': block_hash,
                  'transaction_index': index, 'confirmations': head - block, 'decimals': decimals,
                  'raw_amount': str(amount), 'display_amount': str(displayed),
                  'claimed_amount': str(claimed_amount), 'matched_log_indices': matched}
        if status == 0:
            return Verdict.FAIL, '已确认交易回滚，未完成所声明的转入。', detail
        if not matched:
            return Verdict.FAIL, '完整成功回执中没有目标代币转入预定地址的Transfer。', detail
        if displayed != claimed_amount:
            return Verdict.FAIL, '目标Transfer合计并按正数half-up取整后与声明金额不符。', detail
        return Verdict.PASS, '完整回执的目标Transfer合计与声明整数金额一致；不证明Agent执行归属。', detail
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
        return Verdict.UNKNOWN, '证据缺失、格式错误或来源不一致：' + str(error), {}
