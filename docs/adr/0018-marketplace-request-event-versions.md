# ADR-0018：同一Marketplace的两版普通请求事件

日期：2026-10-18。继续已授权的预测证据扩展，不新增业务类别。2135四个已冻结行为任务不是缺原件：同一可信Marketplace、同一request调用，原件使用四参数事件；当前解析器仅识别五参数事件，故原报告保持UNKNOWN。

建模依据已跨对象核实：2135四槽及2150窗口外固定首条任务均由同一Marketplace发出旧事件，任务ID唯一、Mech/requester匹配，原调用CID与Mech Request CID一致，2150实际交付Mech及历史serviceId也已核对。原件见 `runtime/prediction-event-variant-review-20261018T143954Z-b7b65678/` 和 `runtime/prediction-tail-event-probe-20261018T144713Z-fd097d6e/`，未按评分换样本。

官方固定源码：[父版766fe81](https://github.com/valory-xyz/autonolas-marketplace/blob/766fe81dc2320dc5fa35a4e2e285f9142b4c72ca/contracts/MechMarketplace.sol#L62)定义 `MarketplaceRequest(address,address,uint256,bytes32[])`；[变更2ab683f](https://github.com/valory-xyz/autonolas-marketplace/commit/2ab683fe92b409db1c3185c1099c916e4aca2580)增加bytes[]请求原件。两版Ethereum Keccak topic均与真实保留日志一致。Git日期不是代理升级时间，不据此猜链上切换块。源文件及HTTP/SHA记录见 `runtime/marketplace-event-source-research-20261018T145000Z/`。

纯核验器新增显式事件修订2：仅同一预置信任地址的上述两种准确topic，仍要求唯一事件、正确indexed角色、count/唯一ID、完整ABI形状；五参数继续比事件CID，四参数由原request calldata与独立Mech Request精确比CID。历史服务/执行者、授权、支付上限、接手窗口、交付调用、输出CID和确认规则全部保持。签名/离线请求不自动纳入。

平台V2核验修订4显式选择该事件修订，并延续修订3的实际输出声明核验。默认旧事件修订、V1及已发布修订1/2/3复算保持不变。对同冻结计划可追加新报告，复用原14任务及原10次A，报告说明旧UNKNOWN和本次支持的来源差异，不覆盖旧报告。

必要验证仅一次：两对象真实旧事件在旧修订保持UNKNOWN、新修订独立重验；一个真实当前事件新旧结果相同；缺失/重复任务、角色或CID篡改拒绝。随后真实PG独立重验发布，不重跑旧套件或访问采样。
