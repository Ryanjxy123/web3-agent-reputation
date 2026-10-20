"""Small static business Checker registry over the shared evidence lifecycle."""

from reputation_platform.mech_task_evidence import collect_mech_tasks
from reputation_platform.query_checker import collect_query_tasks
from reputation_platform.position_fulfillment import collect_position_fulfillment

# Prediction retains its existing policy-specific early dispatch; these compose service-contract evidence.
BUSINESS_CHECKERS = (('query.pancakeswap-v3-position', collect_position_fulfillment),
                     ('query.erc20-transfer-record', collect_query_tasks),
                     ('mech.history-delivery', collect_mech_tasks))


def collect_business_checks(registration, evidence):
    capabilities, samples, limitations = [], [], []
    primary_query = False
    for checker_id, collect in BUSINESS_CHECKERS:
        # One primary F task set preserves the seven-task policy for multi-tool Agents.
        if checker_id == 'query.erc20-transfer-record' and primary_query:
            limitations.append('本轮优先评价已匹配的V3仓位能力；ERC20交易记录能力另次评价，不混合F任务。')
            continue
        if checker_id == 'mech.history-delivery' and primary_query:
            continue
        matched, observed, missing = collect(registration, evidence)
        if checker_id == 'query.pancakeswap-v3-position' and matched:
            primary_query = True
        capabilities.extend(matched)
        samples.extend(observed)
        limitations.extend(missing)
    return capabilities, samples, limitations
