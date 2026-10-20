"""Pure five-field PancakeSwap v3 NFT verification; callers bind RPC provenance."""

import re

from reputation_core import Verdict
from reputation_core.disclosure import _position
from reputation_platform.query_oracle import _hex, _quantity

NPM = '0x46a15b0b27311cedf172ab29e4f4766fbe7f4364'
FACTORY = '0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865'
STATIC_FIELDS = ('token0', 'token1', 'fee', 'tickLower', 'tickUpper')


def canonical_position_id(value: object) -> str:
    if (not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]{0,77}', value)
        or int(value) >= 2**256):
        raise ValueError('仓位ID必须为规范的uint256十进制字符串。')
    return value


def position_reference(position_id: str, chain_id: int, npm: str, factory: str,
                       values: dict) -> dict:
    """Validate complete fixed-state raw results, or raise ValueError before a call.

    The caller must separately bind every RPC request to this header's block,
    target contract and tokenId; these values alone cannot prove that provenance.
    """
    try:
        token_id = canonical_position_id(position_id)
        if (type(chain_id) is not int or chain_id != 56 or _hex(npm, 40) != NPM
            or _hex(factory, 40) != FACTORY or _quantity(values['chain']) != chain_id):
            raise ValueError('参考链或受审阅合约范围不一致。')
        head, header = _quantity(values['head']), values['header']
        block, block_hash = _quantity(header['number']), _hex(header['hash'], 64)
        timestamp = _quantity(header['timestamp'])
        if head - block != 64:
            raise ValueError('参考区块不是预定链头减64。')
        for key in ('npm_code', 'factory_code'):
            if not isinstance(values[key], str) or not re.fullmatch(r'0x(?:[0-9a-fA-F]{2})+', values[key]):
                raise ValueError('缺少合约字节码。')
        actual_factory = int(_hex(values['factory'], 64), 16)
        owner = int(_hex(values['owner'], 64), 16)
        if actual_factory != int(FACTORY, 16) or not 0 < owner < 2**160:
            raise ValueError('工厂地址或NFT存在性参考无效。')
        words = _position(values['positions'])
        ticks = [word - 2**256 if word >= 2**255 else word for word in words[5:7]]
        if any(not -887272 <= tick <= 887272 for tick in ticks):
            raise ValueError('仓位tick超出v3协议边界。')
        expected = {'positionId': token_id, 'token0': f'0x{words[2]:040x}',
                    'token1': f'0x{words[3]:040x}', 'fee': words[4],
                    'tickLower': ticks[0], 'tickUpper': ticks[1]}
        return {'chain_id': chain_id, 'npm': NPM, 'factory': FACTORY,
                'position_id': token_id, 'block_number': block, 'block_hash': block_hash,
                'block_timestamp': timestamp, 'confirmations': head - block,
                'reference_owner': f'0x{owner:040x}', 'expected': expected,
                'scope': '五项静态仓位事实；不核动态状态、建议或执行归属。'}
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
        raise ValueError('完整固定区块参考不可用：' + str(error)) from error


def verify_position_record(claim: dict | None, position_id: str, chain_id: int,
                           npm: str, factory: str, values: dict) -> tuple[Verdict, str, dict]:
    try:
        detail = position_reference(position_id, chain_id, npm, factory, values)
        if not isinstance(claim, dict):
            raise ValueError('缺少可适配业务输出。')
        claimed = {'positionId': canonical_position_id(claim['positionId']),
                   'token0': _hex(claim['token0'], 40), 'token1': _hex(claim['token1'], 40)}
        for key in ('fee', 'tickLower', 'tickUpper'):
            if type(claim[key]) is not int:
                raise ValueError('业务费率和tick必须为精确JSON整数。')
            claimed[key] = claim[key]
        mismatched = [key for key, expected in detail['expected'].items() if claimed[key] != expected]
        if 'reportedChain' in claim:
            if type(claim['reportedChain']) is not int:
                raise ValueError('输出链号不是精确JSON整数。')
            if claim['reportedChain'] != chain_id:
                mismatched.append('reportedChain')
        if 'reportedPositionId' in claim:
            reported = canonical_position_id(claim['reportedPositionId'])
            if reported != position_id:
                mismatched.append('reportedPositionId')
        detail.update(claimed=claimed, mismatched_fields=mismatched)
        if mismatched:
            return Verdict.FAIL, '完整独立参考与业务输出的静态事实或任务归属不一致。', detail
        return Verdict.PASS, '五项静态仓位事实与独立固定区块参考一致；不证明执行归属。', detail
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
        return Verdict.UNKNOWN, '参考或输出缺失、畸形，不能确定业务正确性：' + str(error), {}
