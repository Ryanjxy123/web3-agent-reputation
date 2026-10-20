"""Observable delivery, independent of the correctness of business facts."""

from math import isfinite

from reputation_core import Verdict
from reputation_platform.position_adapters import _json
from reputation_platform.position_oracle import canonical_position_id
from reputation_platform.query_oracle import _hex

DEADLINE_MS = 30000


def should_stop_business(observation, raw):
    """Retain the old stops and honor explicit errors inside a tool delivery."""
    from reputation_platform.position_checker import _must_stop

    if _must_stop(observation, raw):
        return True
    try:
        envelope = _json(raw)
        result = envelope.get('result')
        if not isinstance(result, dict):
            return False
        error = None
        if result.get('isError') is True:
            error = result.get('content')
        elif result.get('kind') == 'message':
            parts = result.get('parts')
            if isinstance(parts, list) and len(parts) == 1 and isinstance(parts[0], dict):
                data = parts[0].get('data')
                if isinstance(data, dict) and isinstance(data.get('result'), dict) and 'error' in data['result']:
                    error = data['result']
        if error is None:
            return False
        text = str(error).lower()
        return any(term in text for term in ('rate limit', 'rate_limit', 'too many requests', 'quota',
                   'payment required', 'payment_required', 'authentication required', 'authentication_required',
                   'unauthorized', 'forbidden', 'access denied', 'access_denied'))
    except (ValueError, TypeError, AttributeError):
        return False


def verify_query_fulfillment(observation, raw, request_id, token_id, delivery):
    """The caller authenticates endpoint, exact request, eligibility and raw bytes."""
    if (not observation or observation.http_status != 200 or not observation.body_complete
        or observation.error_kind):
        return Verdict.UNKNOWN, '没有完整可归属业务响应；网络、权限或平台故障不能归责Agent。'
    try:
        envelope = _json(raw)
    except (ValueError, TypeError):
        return Verdict.UNKNOWN, '未取得可归属JSON-RPC业务响应，不能把网页或中间层错误归责Agent。'
    if not isinstance(envelope, dict) or envelope.get('jsonrpc') != '2.0':
        return Verdict.UNKNOWN, '响应不是可归属的业务协议交付。'
    if type(envelope.get('id')) is not str or envelope['id'] != request_id:
        return Verdict.FAIL, '完整协议响应关联了错误请求标识。'
    if 'error' in envelope:
        error = envelope['error']
        # Only reviewed method/input contradictions establish responsibility.
        if (isinstance(error, dict) and 'result' not in envelope
            and type(error.get('code')) is int and error['code'] in (-32601, -32602)
            and isinstance(error.get('message'), str) and error['message'].strip()):
            return Verdict.FAIL, '已确认的接口及有效冻结输入被服务以方法不存在或参数无效拒绝。'
        return Verdict.UNKNOWN, '协议执行错误不能独立排除依赖、费用、权限、配额或对象快照后的变化。'
    result = envelope.get('result')
    if isinstance(result, dict) and result.get('isError', False) is not False:
        return Verdict.UNKNOWN, '工具自报执行错误，没有足够独立证据区分服务违约和依赖故障。'
    if isinstance(result, dict) and result.get('kind') == 'message':
        parts = result.get('parts')
        if isinstance(parts, list) and len(parts) == 1 and isinstance(parts[0], dict):
            data = parts[0].get('data')
            if (isinstance(data, dict) and isinstance(data.get('result'), dict)
                and 'error' in data['result']):
                return Verdict.UNKNOWN, '同步业务返回依赖或对象读取错误，不能仅凭自报错误归责Agent。'
    try:
        if not isinstance(delivery, dict):
            raise ValueError('Missing normalized delivery')
        canonical_position_id(delivery['positionId'])
        _hex(delivery['token0'], 40)
        _hex(delivery['token1'], 40)
        if any(type(delivery[field]) is not int for field in ('fee', 'tickLower', 'tickUpper')):
            raise ValueError('Missing exact delivery types')
        if 'reportedPositionId' in delivery:
            canonical_position_id(delivery['reportedPositionId'])
        if 'reportedChain' in delivery and type(delivery['reportedChain']) is not int:
            raise ValueError('Missing exact chain type')
    except (ValueError, TypeError, KeyError):
        # This is a complete, associated result, rather than a connection success.
        return Verdict.FAIL, '完整关联响应没有交付约定的业务结果或必需字段。'
    if (delivery.get('positionId') != token_id
        or delivery.get('reportedPositionId', token_id) != token_id
        or delivery.get('reportedChain', 56) != 56):
        return Verdict.FAIL, '交付对象或业务链与冻结任务不一致。'
    if (type(observation.elapsed_ms) not in (int, float) or not isfinite(observation.elapsed_ms)
        or observation.elapsed_ms < 0):
        return Verdict.UNKNOWN, '缺少有效的客户端履约计时，不能确认预定观测窗口。'
    if observation.elapsed_ms > DEADLINE_MS:
        return Verdict.UNKNOWN, '完整交付超过预定30秒观测窗口；没有服务端时钟，无法区分网络与Agent责任。'
    return Verdict.PASS, '认证服务对独立合格对象完成了请求关联、完整交付及30秒内可观察履约；不判断业务事实真值。'
