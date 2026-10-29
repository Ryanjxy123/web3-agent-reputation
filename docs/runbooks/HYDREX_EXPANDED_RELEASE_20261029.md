# Hydrex扩采发布记录（2026-10-29）

Hydrex正式v2已追加导入真实PostgreSQL，并在本机7754网站发布。报告ID为`da575ada-2322-47a1-81c8-6f85df1a26a1`；43个实际任务、48个冻结槽位，8笔真实兑换为USDC→WETH和WETH→USDC各4笔。当前范围分为 **A82.22 / F100 / B100 / 综合94.67**。旧pilot、v1中间版本、原冻结计划、失败和UNKNOWN均保留，不覆盖历史。

## 正式输入与范围

| 项目 | 保留路径 |
| --- | --- |
| 正式报告 | `runtime/hydrex-report-20261029-expanded-v2/report.json` |
| 输入清单 | `runtime/hydrex-report-20261029-expanded-v2/manifest.json` |
| 正式来源 | `runtime/hydrex-public-20261029-expanded-v2/source.json` |
| 冻结assessment | `runtime/hydrex-directional-assessment-20261029/plan-v3.json` |

冻结plan SHA256为`fb4314d72fd110dc0947c319e65ea64719598bf7e7c2555ab0f97cc1f3a1d696`，source SHA256为`2d02e5b4e14b6a05581a8d7ea8479715443b8d173e272ed48f4d175e95cfdb74`，report SHA256为`44f16244f31de2c01de42cceb6f86506df6338cf8dae222053cc7f04bce7ddb7`。计划保留previous_plan与原任务时钟，既有证据的回顾映射不冒充前瞻实验。48是冻结槽位数，43是实际观测任务数；服务费、同任务多次读取和模拟不增加实际任务或成交数。

范围为Base链ERC20精确输入路由，核实际交付、原请求与方案绑定、独立固定块效果及本人真实资产变化。8笔兑换均保留实际交易、收据/事件、收款、净资产、授权归零与至少64块确认距离；确认距离不宣称finalized。内部路由source的功能覆盖与双方向真实履约采样分开，不要求四个内部source各自成交才认可已测B。

## 分数与保留的未知

A使用冻结case的可判通过/失败比例，再按现有共享规则汇总，不把全部任务混成一个分母：

| A case | PASS | FAIL | UNKNOWN | case分数 |
| --- | ---: | ---: | ---: | ---: |
| 正向USDC→WETH | 8 | 1 | 3 | 88.89 |
| 反向WETH→USDC | 10 | 0 | 2 | 100 |
| 缺省参数 | 4 | 1 | 0 | 80 |
| source比较 | 3 | 2 | 0 | 60 |

四个case等权汇总为`(88.89 + 100 + 80 + 60) / 4 = 82.22`（展示取两位）。4项超时为H38（2146秒）、H17缺收款地址（360秒）、H22 OpenOcean（498秒）、H23 OKX（404秒），均超过冻结300秒窗口。结论来自完整链上事件窗口及窗口之后取得的官方history，未将较早快照当作完整超时证据。A共有34个观测任务，其中25 PASS、4 FAIL、5 UNKNOWN；它与43个全范围实际任务的口径不同。

F100表示本范围可判的功能判据均通过：正式报告有73项PASS、73项UNKNOWN、0项FAIL。任务级摘要的“完全符合1/43”要求同一任务相关判据全部可判且通过；多数任务已有交付格式、意图或效果PASS，但source归属等仍未知，所以不能把它解释为只通过1个判据。声明覆盖与F覆盖均为PARTIAL，不把UNKNOWN补成通过，也不声称43个任务全部功能已验证。

网站F卡另列功能判据“通过73、不符0、未知73”，只统计measurement_validity=valid的functional观察，并按task_key＋criterion_id去重；下面“完全符合／含不符／未验证”仍表示整任务完整程度。分层汇总与权重仍在原评分方法折叠中，分数、后端、schema和报告原件不变，未新增对象名分支或布局样式。必要的一次前端检查`pnpm --dir apps/web run build`包含`vue-tsc --noEmit`与Vite，exit0，Vite构建541ms；未重跑旧tests，未做浏览器/HTTP复核或重启。

- H13已在10秒内交付；方案含尚未识别的BASIC外部AMM，相关意图/效果/source判据保持UNKNOWN，不当作Agent失败。
- H33边界slippage的独立安全拒绝语义未证实，保持UNKNOWN；非法输入未执行本金。
- H24的Kyber source归属另有官方固定commit部署资料、Exact Match及同块runtime核验，`route-filter`为PASS；固定块53222831的完整模拟也通过。它不代表所有内部pool/path均已解码，也不把模拟记为成交。

B100对应双方向各4笔已核正常兑换。保护退出和缺少实际执行的任务不补B分母。综合分按原权重计算：`82.22 × 30% + 100 × 40% + 100 × 30% = 94.67`（两位展示），未改三维权重或阈值。

## 网站与必要修复

Hydrex列表、正式报告、附件已由root核HTTP200，附件SHA与原字节一致。H47任务链证据接口也已复核HTTP200：展开8项同交易调用，含1次swap，仅引用`0xa9ac0e3b1649fc5bdf819f36b1c6b04deb30c887f582d41279a14485e6a56457`，未混入同批3笔ACP服务费交易。无task_key时继续使用首样本摘要布局。

本次只修展示层：按已认证observation的JSONRPC方法读取同目录正文，核完整200、无错误、请求响应与SHA一致；按source中原任务绑定的execution交易筛选。已知无执行任务不借用其它任务/服务费履约；retained-source指针和旧body路径兼容。首次定向核验发现H02 retained指针被误当未执行任务，修复后只重跑同项，最终 **1 test / 0.938s / exit 0**：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_report_chain_campaign_observations.py -v
```

该工程核验使用公开H47/H02原件的可移植夹具，另有明确受控负例，不是新增业务样本。未重跑旧suite；`git diff --check`退出0。最新进程收据为`runtime/background-platform-20261029T012150Z-85ffe9ea/process.json`，worker仍为public-off。文档整理没有重新请求网络、操作钱包、写PG或重启网站。

## 三对象公开包

新包`data/public-reports-trading-expanded-v3.tar.gz`包含MangoSwap34任务/96.67、Topaz38任务/99.2、Hydrex43任务/94.67及必要依赖。归档5693428字节、4272文件，SHA256：

```text
58dd653440e4be9fb24b5f7f8115943bbb6050ca5b2b62954c498a25b3e3f2d7
```

独立离线包verify最终 **exit 0**：3份报告重放成功，恢复4251份runtime文件，0网络请求、0数据库操作。收据为`runtime/package-review-trading-expanded-20261029/verification-receipt.json`。初次隔离环境缺少公共前置；按原清单hash补齐22份文件（18份受Git跟踪文件及4份已审核公共ADR）后通过，归档、业务原件、报告与评分代码未改动。使用包前需保有本仓库当前代码和公开配置，包恢复与本机PG/网站发布分别验收。

root另对4273个归档成员进行了3类实际本机credential的精确比对，0命中；收据`runtime/package-review-trading-expanded-20261029/exact-secret-scan.json`不记录secret值或其hash。此处只引用扫描收据，未读取secret。安装依赖、配置自己的`.env`数据库后，导入入口为：

```powershell
uv run --env-file .env --no-sync python scripts/public_reports.py import data/public-reports-trading-expanded-v3.tar.gz --initialize
```

旧`public-reports-transaction-v3.tar.gz`与Mango历史包保留；不删除旧包、报告或个人数据库。浏览已有报告不需要RPC、LLM或钱包，新增采证使用自己的可信配置；私钥、签名器、登录和私有配置不随包分发。继续严格禁止发币、tokenize及发行身份/报告NFT。

## 收口范围更新

用户随后取消十对象目标：保留MangoSwap、Topaz、Hydrex的正式成果，仅完成已开始正式采样的Ophis后停止新增实验。候选调查保留备查，不再付款、签名或继续适配。最新发布状态以README与STATUS为准；本记录及三对象包保留为Hydrex扩采时的历史交付。
