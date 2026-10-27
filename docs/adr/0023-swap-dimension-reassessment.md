# ADR-0023：兑换评价的独立完整维度复评快照

日期：2026-10-27。状态：在任何复评新窗口开始前固定；本稿在新manifest/采样尚未发生时一并明确A和F复评。沿用`evm-swap-builder-v1`；不修改ADR-0022、原campaign、原任务、评分公式、权重或样本门槛。

## Router02 方法签名勘误

ADR-0022开头方法签名的文字多写了一个`uint256`；该原文件已被原campaign按SHA冻结，保持不改。真实固定Router02、全部原始请求/响应calldata、采集器ABI以及判据的七个字段从始至终对应无deadline的七字段方法：

`exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))`

字段为tokenIn、tokenOut、fee、recipient、amountIn、amountOutMinimum、sqrtPriceLimitX96；目标为已核Base Router02 `0x2626664c2603336e57b271c5c0b26f421741e481`，方法选择器`0x04e45aaf`。独立源码审查在正式报告发布前发现纯规则实现常量沿用了该文字笔误，现修正为真实七字段签名。不存在为分数而变更服务请求、交易参数或门槛，也不把平台实现错误记为Agent FAIL。Metadata的deadline依然不在这项链上调用中。

## 决定

原批十个A槽中，七个真实业务请求取得确定结论，另外三个因操作者RPC或客户端传输故障为UNKNOWN；F06也出现客户端传输失败。原批保留PARTIAL及其全部槽位；不把费用已结算、nonce状态或后续成功请求回填成原请求成功，不删除或替换失败槽，也不将第十一个A观察或第八个F任务塞进原计划。

允许按用户已确定的按需更新原则，在修正已证实的客户端传输问题后追加一次**完整、前瞻的维度复评窗口**。本轮更新完整A10和F7，新十七槽使用新CSPRNG任务ID，参数、顺序、发送间隔和全部槽位在第一次新请求前冻结；A仍须十槽全部保留且至少八个确定结论，F仍须七个全部确定结论才出分。不能采到足够通过就停止，也不能根据结果选择成功请求。若修正后仍存在实质阻塞，保留PARTIAL并停止等待用户决定，不循环开窗刷到通过。

不更新的维度只能完整引用原campaign中已预先冻结的整组正式任务。本轮保留原B7：任务ID、用途、参数、文件路径和SHA逐项不变，包括任何FAIL或UNKNOWN。不能只挑PASS、跨F/B使用同一任务，不能引用可行性pilot充数。所有更新维度的新ID不得与父campaign任何任务重合。保留维度必须从同一组原件确定性重放，而不是从旧报告复制数字。

这是同规则下的复评与已有证据再利用，不是新业务专项或降低充分性门槛。原A/F窗口、原PARTIAL报告及原证据保留；新报告单独追加，明确A/F新窗口和B原正式样本的真实时间范围，不声称二十四个任务都是这次新请求，不把旧交易解释为当前服务保证。

## 显式来源与核验

新manifest仍用`swap-campaign-v1`并显式增加：

```json
{
  "reassessment": {
    "kind": "dimension-window-refresh-v1",
    "policy_note": "docs/adr/0023-swap-dimension-reassessment.md",
    "renewed_purposes": ["availability", "functional"],
    "retained_purposes": ["behavioral"],
    "parent_campaign": "runtime/原批次/campaign.json",
    "parent_campaign_sha256": "原manifest的真实SHA256"
  }
}
```

此处路径和SHA仅为字段说明，不是可运行的伪造证据。实际新manifest必须在首次新请求前绑定本ADR、ADR-0022、原计划、父manifest及任务SHA。身份、端点、执行链、买方和政策与父一致；二十四个逻辑槽位结构保持A10/F7/B7，更新和保留维度必须明确且构成三个维度的无重复分割，保留维度整组与父逐项相等。

核验器检查任意父manifest的实际SHA及其原冻结来源，遇多级复评递归核回原正式计划并拒绝循环。保留任务使用原冻结时刻验证观察时间，新任务使用新manifest冻结时刻；不简单放松“必须先冻结”的检查。新旧报告各自保持来源、样本、范围和计算结果可离线复核。

客户端fetch或读取响应时失败，如已有真实传输异常receipt，只保留实际开始/失败时刻、耗时与错误类别，不要求不存在的响应正文或receivedAt，不把失败传输当Agent FAIL。旧A10没有这类receipt，不补造计时。只有原业务请求实际发送并完整返回，才可能成为A成功样本；前置RPC故障仍为UNKNOWN。
