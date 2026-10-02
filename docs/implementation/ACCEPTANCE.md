# 验收矩阵与完成定义

本文件定义目标，不代表测试已执行。实际状态只见STATUS与run records。人工打勾必须有命令、退出码、记录文件、commit。

## 1. 分层命令契约
下列为Codex应实现的目标入口，除标注已提供者外，不能当现成命令使用。
| 命令 | 内容 | 首次阶段 |
|---|---|---|
| `python scripts/check_bootstrap.py` | 已提供：JSON与评分参考离线测试 | 当前包 |
| `python scripts/git_doctor.py` | 已提供：只读Git诊断，无远程写入 | 当前包 |
| `uv run reputation doctor` | 工具、配置、链指纹/部署/服务检查 | M0/M1 |
| `uv run reputation migrate` | 单Alembic head真实迁移 | M0 |
| `uv run reputation deploy-local` | 显式部署，输出受信runtime | M1 |
| `uv run reputation seed` | 幂等注册/ledger/真值准备 | M1 |
| `uv run reputation demo --suite minimal` | 正常+无关tx+篡改 | M1 |
| `uv run reputation demo --suite full` | A–H及完整20/10/10测试 | M2 |
| `uv run reputation test --suite all` | 真正core/合约/DB/安全/E2E，不是仅reference | M4 |
| `uv run --package reputation-verifier reputation-verify BUNDLE --offline` | 不连接API/DB的包复核 | M1 |
| `uv run --package reputation-verifier reputation-verify BUNDLE --trust-config FILE` | 受信链配置的在线复核 | M1 |

测试目录命名跟架构一致；若CLI实际名变更，必须一次性同步README/脚本/CI/本文件，禁止口头约定。

## 2. M1必须同时满足
1. 从真实API入队，由独立worker调用fixture；不是mock绕过服务。
2. A在Anvil产生真实record事件，与当前request/hash/executor/target匹配。
3. D返回真实receipt成功的旧/无关tx，业务断言FAIL；失败来源可逐字段查看。
4. RPC故障产生UNKNOWN，不出现凭空0分；M1小样本综合分null，未降低policy阈值。
5. 相同request重试、worker中断、fixture重启后，无重复业务record。
6. 导出含观测/断言/统计/策略/manifest/report；真实anchor成功与独立online读取吻合。
7. 未改包offline/online对应步骤通过；改响应或分数失败；删证据显示INCOMPLETE；原包上链后整包重算篡改仍与锚定不符。
8. Repo无privatekey/token/运行数据库；README陌生成员能复現，STATUS如实写未完成项。

有一项缺失M1不能PASS。部署失败、网络受阻、未装Foundry等可以BLOCKED，但不是“逻辑已完成所以通过”。

## 3. 全量FR追踪
| 原PRD | 本包落实位置 | 必测断言 |
|---|---|---|
| FR-01 添加身份 | DOMAIN/API，M0-03/M1-03/M4-01 | 复合唯一、超大ID、source区分 |
| FR-02 快照 | DOMAIN/ERC8004 | owner/URI版本、失败证据、区块绑定 |
| FR-03 有限声明 | EVALUATION，M2-01 | 原文span、否定、人工确认、未覆盖 |
| FR-04 异步恢复 | SECURITY_AND_JOBS，M1-04/M3-03 | 幂等、租约、fencing、未知发送 |
| FR-05 可用性 | EVALUATION，M2-02 | 20槽位，首attempt，平台故障排除 |
| FR-06 声明一致性 | EVALUATION，M2-01/02 | 独立真值、正确拒绝、映射未知 |
| FR-07 任务行为 | EVIDENCE_AND_CONTRACTS，M1-05 | chain/executor/contract/request/hash/finality |
| FR-08 四态评分 | reference+M2-02 | 零样本/只读/Q/golden/阈值边界 |
| FR-09 报告历史 | M1-06/M3-01/03 | 不可覆写、当前有效性与历史分离 |
| FR-10 摘要上链 | M1-01/07 | 权限/nonce/prev/receipt/reconcile |
| FR-11 独立复核 | M1-07 | 脱离API/DB、重算断言、可信配置 |
| FR-12 安全审计 | M0-05/M3-02 | roles/SSRF/DNSpin/zip/secrets/audit |

## 4. 风险测试必须显式编号
T-ID：旧snapshot签名、跨Agent复用、超期nonce、错链、owner变化、agentWallet误用。
T-TASK：旧request、错input、wrongcontract、事件伪装地址、错executor、revert、nullreceipt、pending、reorg。
T-SCORE：PASS/FAIL/UNKNOWN/NA分母；只读不发write；duplicateattempt；negativecase；样本缺失；critical veto；Q舍入不过线。
T-PACK：blob/manifest/policy/report逐个改动；删文件；extra文件；重复JSONkey；非法UTF8；zip目录穿越/重复大小写名/链接/炸弹。
T-NET：127.0.0.1、RFC1918、169.254、IPv6 loopback/linklocal/mapped、域名解析多IP、DNSrebinding、重定向、userinfo、URL编码绕过、超大/深JSON、可信RPC与不可信URI路径分离。
T-JOB：抢任务、过期worker写回、发送崩溃、撤销grant、重复anchor、nonce冲突、RPC暂停、链重置、证据文件缺失。
T-UI：UNKNOWN非0；Q非概率；源标签；旧版警告；三步复核分别结果；角色权限；API错误可读。
所有预设测试失败必须保留记录，不能删除样本让测试绿。

## 5. 记录格式
每次验收生成 `artifacts/test-runs/<UTC>-<commit>/summary.json`（默认Git忽略）：
```json
{"schema_version":"test-run-v1","commit":"ACTUAL_COMMIT","dirty":false,"suite":"minimal","environment_file":"environment.json","results_file":"results.json","status":"NOT_RUN","commands":[],"limitations":[]}
```
ACTUAL_COMMIT由程序读取；本示例不是实际结果。正式报告应包含总数/通过/失败/跳过/阻塞、源数据和真实耗时；关键测试skip时gate不能PASS。
参考评分测试不等于链/网络/安全测试；本包交付时未执行任何用户仓库集成验收。
