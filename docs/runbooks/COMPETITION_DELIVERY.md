# 比赛交付检查与源码打包

本文件是任务 13 的交付门槛，不代表最终验收已通过或正式 Release 已发布。运行与现场 A/D 演示见 [DEMO_AND_RELEASE.md](DEMO_AND_RELEASE.md)；具体测试、Review、提交和 CI 状态以 [STATUS.md](../implementation/STATUS.md) 为准。

## 1. 官方要求核查

2026-10-12 检查仓库 README、PLAN、BACKLOG、runbooks 与 references：只有项目自身的比赛目标和匿名提醒，没有赛事官方规则、赛事名称/官方提交链接、截止日期、材料模板、视频/演示时限、评分表或匿名细则原件。因此这些要求均为 `UNVERIFIED`，不能自行编造为已满足。

正式赛事提交前由负责人取得并核对官方规则，记录原件链接/版本、对应材料及实际截止时间。当前按用户要求准备源码、技术说明、实验、测试、演示和已知限制，不能替代官方清单。缺官方材料不阻断软件开发、测试或按用户授权发布软件 Release；Release 需明确披露这些限制，不能声称已满足比赛全部材料要求。

## 2. 内容与技术证据

已有技术说明按职责维护，优先引用这些原件：

- 背景、应用场景、模块：[README](../../README.md) 和 [架构](../architecture/ARCHITECTURE.md)。
- 可信身份、版本与 ERC-8004：[领域](../specs/DOMAIN.md) 和 [ERC-8004](../integrations/ERC8004.md)。
- 三维公式、充分度、四态及风险：[评价规则](../specs/EVALUATION.md)。
- 真实任务、Evidence Bundle、独立复核：[证据与合约](../specs/EVIDENCE_AND_CONTRACTS.md) 和 [ADR](../adr/)。
- 安全出口、授权、幂等、租约与秘密管理：[安全与恢复](../specs/SECURITY_AND_JOBS.md)。
- 部署、演示与公共只读：[本地运行](LOCAL_RUNTIME.md)、[演示](DEMO_AND_RELEASE.md) 和 [公共只读评价](PUBLIC_READONLY_EVALUATION.md)。

任务 11 的原始数据、指标、图表、环境和复现命令必须来自已验收的实际执行；任务 12 的页面、操作和自动化检查必须连接后端。静态手写 verdict/timing、页面 Mock 或旧版本结果不能作为正式实验/前后端联调证据。

## 3. 指定 commit 的源码交付包

`scripts/package_delivery.py` 使用 `git archive` 导出指定 commit 的已跟踪文件，不复制工作树、.env、runtime 或本地数据库。若该 commit 跟踪了禁止的秘密/runtime 路径，脚本在生成输出前拒绝。它不判断 CI、安全验收或匿名是否通过；清单明确标为 `NOT_ASSERTED` / `NOT_REVIEWED`。

正式候选应先提交已验收改动，核对工作树干净，再导出目标 commit：

```powershell
$changes = git status --porcelain
if ($changes) { throw 'Commit and review the intended changes before final packaging.' }
$commit = git rev-parse HEAD
$output = "runtime/delivery-{0}" -f $commit.Substring(0, 12)
uv run --all-packages python scripts/package_delivery.py --ref $commit --output $output
```

输出目录必须不存在，脚本不覆盖旧包。产物是 `source.zip`、逐文件 SHA-256/字节数与实际 commit 的 `manifest.json`、以及 `licenses.json`。相同 commit 的源码字节来自 Git 对象；未提交修改和忽略文件不会改变包。公开证据 ZIP 只来自已经审过并跟踪的脱敏文件。

禁止路径检查不能替代内容审查：发布前仍须检查跟踪的源码、报告、图像和 ZIP 内是否含凭据或未脱敏信息。不要因为文件已提交就假定可以公开。

从 ZIP 运行时不含 `.git`，需先核对 archive SHA-256 与 manifest 一致，再在 API/worker 启动终端设置实际 commit；否则冻结报告不能得到具体源码版本：

```powershell
$manifest = Get-Content ./manifest.json -Raw | ConvertFrom-Json
if ((Get-FileHash ./source.zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.source_archive_sha256) { throw 'Source archive checksum differs.' }
$env:CODE_VERSION = $manifest.commit
```

`CODE_VERSION` 只承诺已核对的原始字节；修改导出源码后不能继续声称原 commit。实验 `capture` 记录 Git 信息，按 Task 11 runbook 从目标 commit 的 Git checkout 运行；已保留的实验输出和 Evidence Bundle 的离线分析/复核可独立运行。

源码包尚未做匿名审查：README/历史文档可能含 GitHub 链接、成员信息或本地路径。若官方规则要求匿名，生成单独材料副本并审查全文及图像；保留必要第三方许可来源，不改写团队 Git 历史。

许可清单记录 NOTICE/UPSTREAM_README 和锁文件哈希，不能替代完整依赖许可审查。当前仓库没有根目录 LICENSE；清单将标为 `first_party_license=NOT_DECLARED`，不自动赋予第一方许可证。依赖元数据核查记录见 [DEPENDENCY_LICENSE_METADATA.json](../references/DEPENDENCY_LICENSE_METADATA.json)；元数据声明不代表已核查所有发行文件或再分发义务。Release 应保留来源/notice 并披露第一方许可未声明与许可审查范围；这些已知限制不新增用户授权以外的审批或 Release 阻塞。

## 4. 最终 Release 清单

- [ ] 任务 11/12/13 实现、定向测试、独立 Review、修复和重测均有证据；STATUS 与最终代码一致。
- [ ] 全量 Python 为 0 skipped；Ruff、Mypy、Schema/TS 漂移、Web 类型/构建/自动化测试、Foundry/fuzz/ABI 均通过。
- [ ] 真实 PostgreSQL、Anvil、API、worker、Verifier、A/D 历史 Bundle、恢复与部署 smoke 通过；第三方失败/限制另行记录。
- [ ] 实验原始数据、统计、图表和报告一致，适用范围/分母/UNKNOWN/N/A 正确，样本不足不宣称显著性。
- [ ] 前端身份/绑定、充分度、风险、overall=null、UNANCHORED 与后端一致；关键交互/异常有自动化与真实 API 验证。
- [ ] 指定 commit 全部 required CI 通过；PR 无冲突并遵循审批；最终 main 与 origin/main 一致、工作区干净。
- [ ] 源码、日志、证据、ZIP 与附件无私钥/token/未脱敏敏感材料；保留第三方 notice，准确披露许可/官方规则/匿名材料的核查范围和未核实事项。
- [ ] 发布清单记录版本、实际 SHA、完整测试记录、交付包 SHA-256、已知限制和复现命令。

只有软件最终验收与 required CI 全部通过后才 tag 并按用户授权发布正式软件 Release。正式赛事提交另须核对官方材料、截止时间、匿名及许可声明要求；软件 Release 不等于官方赛事资格或材料已满足。打包命令不创建 tag、上传文件、发布 Release 或发送消息。未完成项保持 NOT_RUN/BLOCKED/准确限制；旧失败记录不得删除或覆盖。
