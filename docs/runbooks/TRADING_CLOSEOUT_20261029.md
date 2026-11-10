# 四个真实交易Agent的收口发布记录（2026-10-29）

用户取消十对象数量目标后，本轮完成已正式在测的MangoSwap、Hydrex、Topaz和Ophis。四份已测范围评价已导入真实PostgreSQL并在本机网站发布；已停止新增Agent实验。其它候选的调查、拒绝和缺源记录保留，不继续启动请求、付款、授权或适配。合计146个实际任务、32笔真实兑换及2笔订单管理，未发币、未tokenize、未发行身份或报告NFT。

## 正式发布结果

| 对象 | 实际任务 | 真实兑换 | 其它实际履约 | A | F | B | 综合分 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MangoSwap | 34 | 8 | 2笔订单管理 | 100 | 91.67 | 100 | 96.67 |
| Hydrex | 43 | 8 | 0 | 82.22 | 100 | 100 | 94.67 |
| Topaz | 38 | 8 | 0 | 100 | 98 | 100 | 99.2 |
| Ophis MCP | 31 | 8 | 0 | 100 | 100 | 100 | 100 |

任务数是实际观测任务数；同任务的报价、构建、验证、RPC读取和多条判据不重复计数。Hydrex有48个冻结槽位，其中43个实际任务；不能把48当作已执行数量。MangoSwap的2笔订单管理验证创建、查询、撤销与退款，不能额外称为兑换。API服务费、钱包资金调拨、模拟及未提交订单均不计实际成交。

| 对象 | 当前正式报告ID |
| --- | --- |
| MangoSwap | `2c7ded39-f808-40b0-8d15-dddebee21704` |
| Hydrex | `da575ada-2322-47a1-81c8-6f85df1a26a1` |
| Topaz | `bcbbaaea-df0c-47cb-ad70-31a6e08a3478` |
| Ophis MCP | `6e32f752-1c49-4003-89a4-3d4e38902b42` |

四份报告共用服务可用性、功能声明一致性、交易行为可靠性及30%/40%/30%权重。一个任务为不同维度提供不同事实，按任务、维度、判据去重；UNKNOWN和未采不补通过，也不统一扣Agent分。单分来自有效可判结果，声明覆盖和证据充分性另外呈现。完成本轮采样不等于验证全部声明或证明未来表现；全声明覆盖不是出已测范围综合分的强制门槛。

MangoSwap的资产名称标注差异仍影响F；Hydrex的4项完整窗口超时仍影响A；Topaz的真实非法输入响应不符仍影响F。这些差异来自已保留证据，没有为了避免满分而人为扣分。Hydrex扩采细节见[对应发布记录](HYDREX_EXPANDED_RELEASE_20261029.md)，MangoSwap单分依据见[ADR-0029](../adr/0029-single-score-and-report-scope.md)。

## Ophis的声明、任务和链上履约

Ophis是公开MCP服务，提供CoW Protocol报价、待签名订单构建、校验等工具。服务生成订单，买方钱包签名和精确授权，solver在Base链结算。登记服务、买方签名账户与solver交易发送者分别核验，不能因交易`from`是solver就把买方资产归属丢失，也不能把买方钱包当作服务自己的执行账户。

身份为`mcp-registry:fi.ophis/mcp@0.2.0`。官方MCP具体name/version及remote已核实，`public_registry_verified=true`；尚未核实ERC-8004链注册，`chain_registration_verified=false`，该项为背景UNKNOWN，不冒充链上注册，也不进入A/F/B分母。

正式31任务保留原30任务和追加C31的全部观察。8笔实兑为USDC→WETH、WETH→USDC各4笔；原C02因本地时效保护未submit，已清零精确授权，不能算成交。fresh C31在新计划冻结后请求并完成，原C02仍留在报告。每笔实兑均核原UID、完整独立order/trades、canonical Settlement Trade、本人收款与净资产、签入最低值、期限、结束授权为0及至少85块距离；既有门槛仍64块，确认距离不宣称finalized。

| 维度 | 当前证据与解释 |
| --- | --- |
| A 100 | 24个可判正常任务均取得完整业务响应；p95为16764ms。没有公开SLA时不虚构时限，延迟另行列出。 |
| F 100 | 93项PASS、0项FAIL、15项UNKNOWN。严格整任务计数为16通过、15未知；不是31个任务的所有功能全部通过。 |
| B 100 | 8个正常实兑PASS，原C02保留1个UNKNOWN；保护退出不能补正常实兑分母。 |
| 声明覆盖 | PARTIAL；独立余额、同期盈余基准及原生submit公开证据仍有缺项。 |

C16请求声明允许的短生命周期，在验证阶段已低于声明要求的剩余60秒，工具触发时效保护；对应正常验证项保留UNKNOWN。C24故意改变appCode且同步其哈希，工具按声明给出明确归因告警，属于告警检查PASS，不要求声明没有承诺的fatal拒绝，更不表示成交。回顾解释校准单独绑定测量契约及[ADR-0041](../adr/0041-cow-declared-diagnostics-calibration.md)，原冻结计划和原响应不改。

余额响应没有区块编号，事后当前RPC不能补成同块余额正确。盈余两次内部算术结果为-215/-346bps，但缺独立同期上游报价与时钟，市场基准仍UNKNOWN，负盈余本身不扣功能分。原生submit的私密签名请求不随公开包分发，不能把独立已成交反推为该公开工具已完成可复核验证。

## Ophis正式输入与不可改原件

| 项目 | 路径或SHA256 |
| --- | --- |
| 追加冻结计划 | `runtime/ophis-cow-campaign-20261029/plan-v2.json` |
| 计划SHA | `188540b1dbcc8cd5208495fbe339fa34bec1e078b37544329fc01b7745ea6dc6` |
| 测量校准契约 | `runtime/ophis-cow-measurement-calibration-20261029/measurement-contract.json` |
| 契约SHA | `c72173d6160304433243bdfbc4d00461f159ac2a2da0afab684e0e8d0e866b28` |
| 正式来源 | `runtime/ophis-public-20261029-calibrated-v1/source.json` |
| 来源SHA | `d59ac1e24944923be00eb050702a27daba59bc1f457985288477a9d898293017` |
| 正式报告目录 | `runtime/ophis-report-20261029-calibrated-v1` |
| report.json SHA | `ef2012819fd06dcbe53b6d5536a677453c549659d7c3c5d7d06e0b8ade90acfa` |
| manifest.json SHA | `259939a7e1c9cfa6153bc581e85f30f9127abd44377fabe4a96b15e5ff2a6f00` |

装配器按原任务UUID与意图、精确计划版本、原生HTTP阶段顺序、独立执行状态及原观察时钟选取公开原件；不按随机状态目录名选结果。C01只复用旧pilot真实原件，不采用测试fixture里的受控计划。相关方法见[CoW原件装配](../research/COW_TASK_ITEM_ASSEMBLER_20261029.md)及[ADR-0040](../adr/0040-cow-append-only-campaign-lineage.md)。签名器、私钥、私密请求和发送围栏不进入公开source。

## 网站与必要工程核验

本机入口为[http://127.0.0.1:7754/](http://127.0.0.1:7754/)，Ophis入口为[对应报告页](http://127.0.0.1:7754/?agent=mcp-registry%3Afi.ophis%2Fmcp%400.2.0)。真实PostgreSQL导入及HTTP已经核验：四对象列表、Ophis含斜杠标识详情、正式报告、C08任务链视图与证据附件均HTTP200，附件SHA与保留原件相等。C08只展开1笔真实CoW兑换。回执：

```text
runtime/ophis-cow-publication-20261029/http-verification.json
runtime/background-platform-20261029T031902Z-ad7aae02/process.json
```

worker保持public-off；浏览报告不触发新增付费任务或资产交易。CoW链视图实际重放耗时4281ms，CI smoke的本机HTTP超时已据此改为15秒，不改变服务评分SLA。

本轮只对新行为执行必要定向核验，已有有效结果直接复用：

| 核验 | 结果 | 范围 |
| --- | --- | --- |
| 声明诊断校准 | 1 test / 1.281s / exit 0 | 时效保护、具体告警、缺告警/fatal负例、旧无契约兼容与来源SHA |
| 已完成核验/成交标签 | 1 test / 0.808s / exit 0 | 非成交的告警检查不显示为已成交 |
| 公开余额RPC路径准入 | 1 test / 0.002s / exit 0 | 28份真实路径、22项私有/错误布局负控，见ADR-0042 |
| 含斜杠标识路由 | 1 test / 0.365s / exit 0 | encoded MCP key、旧key的详情/链证据/附件和404；TestClient+mock仅验路由 |

路由测试不冒称PostgreSQL集成；真实PG/HTTP结果另有上方回执。未为提交或改文档重跑旧suite。最终CI仍按仓库required checks执行，其状态以Git交付回执为准。

## 四对象公开包与复现

最终公开包：`data/public-reports-trading-closeout-v4.tar.gz`。

最终四对象包`data/public-reports-trading-closeout-v4.tar.gz`已通过独立离线verify（exit 0）：4份报告、4917份runtime恢复、25份Git原字节环境前置，0联网/0数据库写入。归档6381791字节、4941文件（含索引4942成员），SHA256 `9cbf2cfff85f7b1af9ef16fce542488f7217773838cd3c19d6a50c90a9f3460e`；3类已知本机秘密及私钥标记扫描0命中。回执见`runtime/package-review-trading-closeout-20261029/verification-receipt.json`和`exact-secret-scan.json`。

分发器首次误拦已认证的`balance-after`原件，按[ADR-0042](../adr/0042-public-fixed-block-balance-after-path.md)仅扩展规范公开RPC路径后通过；原件、报告、评分和私密路径拒绝规则未改。

旧三对象包`data/public-reports-trading-expanded-v3.tar.gz`已核验并保留为历史；其3份重放、4251份runtime恢复和秘密筛查结果不能作为新四对象包通过的证据。旧报告、原source、冻结计划及其它历史包均不覆盖。

最终包已通过核验，安装依赖、构建前端并配置自己的数据库，使用：

```powershell
uv run --env-file .env --no-sync python scripts/public_reports.py import data/public-reports-trading-closeout-v4.tar.gz --initialize
uv run --env-file .env --no-sync python -m uvicorn reputation_platform.api:create_app --factory --host 127.0.0.1 --port 7754
```

另开终端按README启动public-off worker。导入与浏览已有报告不需要RPC、LLM、钱包或充值；新增采证才需操作者自行配置。已有个人数据库不因拉代码或导入自动清空。私有数据库连接、登录会话、P256签名器与钱包私钥不随仓库分发。

## Git交付与后续边界

分支为`codex/hydrex-expanded-evaluation`，代码检查点`a80f327`已commit；本轮通过该任务分支提交最终代码、数据与文档PR。最终提交、push、PR与required CI状态入口为：

```text
runtime/release-closeout-review-20261029/git-delivery.json
```

未见该最终回执前不猜测已经推送或合并。保留无关`docs/presentation/`及队友视觉成果，不重开已撤回的PR21，不改写共享历史。完成本次包与Git交付后等待用户反馈；不因旧十对象计划、余额或仍有候选资料而自动恢复实验。
