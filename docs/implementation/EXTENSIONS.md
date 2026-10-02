# 队友扩展指南

先读AGENTS、DOMAIN与对应spec；从main更新后建短分支，不在他人未完成目录里批量重构。核心目录的共同契约必须评审。

## 1. 新增一个能力（例：新增某种凭证有效期核验）
1. 先定义可判定真值、输入/输出Schema、正向/负向用例、风险级别、授权与允许合约；不把“模型觉得正确”设为真值。
2. 在core/capabilities新增版本化模板，实现plan/assert_result，产出已有TaskEnvelope/Assertion，不直接调HTTP或DB。
3. 在可信静态registry登记ID，增加声明词典和原文span测试。解析器只给candidate，仍需confirm；适配器没有实现就unknown。
4. 增fixture正常/异常模式及至少10个功能case；purpose独立，不把同一case用于提升多个分数。
5. 更新profile/schema版本；是否改变原有必需覆盖是策略变更，必须生成新policy，不直接污染历史v1。
6. 跑单元→协议contract tests→真实链集成→独立verifier重算→UI证据展开。提交包含SOURCE/许可、失败路径、兼容说明。

通常改动只应涉及capability模块、静态registry、字典/数据集、fixture、测试。若必须大改DB/API/评分器，先检查是否泄露协议字段到领域层，再写ADR。

## 2. 新增协议适配器（如A2A或MCP）
- 在platform/adapters/protocols实现统一execute/lookup；原始字节与规范化观测都保存，附protocol/version。
- 可读Card不等于完整执行。先锁规范版本，再支持认证、异步任务状态、超时、幂等、安全出口；协议不可证明幂等时写任务禁止自动重发。
- 不修改核心score公式，不让适配器直接输出“90分”，不从响应文字动态启用新工具。
- adapter contract test用同一输入验证controlled-http与新协议输出可被同一assertion处理；补协议专属异常测试。

## 3. 新增评分/充分度算法
- 新增policy-v2文件、内容hash、策略实现和golden；保持v1继续可复算。
- 输入仍为固定证据/断言/槽位统计与评估时间，禁止联网和隐式now；参数选择理由和校准数据范围公开。
- 重算同run生成新report revision并指明policy与supersedes，不覆盖旧结论；报告对比默认不跨policy。
- 概率置信度需要校准证据；无数据时只称规则指数。避免对少样本拟合出看似精确概率。

## 4. 引入大模型
- 只能先替换ClaimExtractor，受Schema、白名单与原文引用校验；输出不合法/不确定返回待确认。
- 记录模型/provider/version/prompt hash与输入脱敏策略；缺key不影响规则版基础demo。
- 不允许模型决定访问内网、执行交易、扩张grant或直接评分。所有外部文本均当不可信数据。
- LLM工具Agent可成为新fixture类型，但保留确定性样本用于回归，单独记录非确定性限制。

## 5. 数据与Schema演进
DTO是唯一领域数据来源；生成OpenAPI/JSONSchema/TS时不手改generated。Breaking change新schema major，同时给旧报告verifier路径。
数据库迁移先讨论单head冲突；append-only实体只能新增版本或状态事件，不能用后台SQL“修评分”。对现有历史包做向后验证测试。

## 6. Code Review重点
A集成：DB约束/队列恢复/API幂等；B评价：真值/分母/unknown；C链：绑定/事件/最终性/哈希；D前端：证据入口/source/partial/版本。
共享Schema、policy、合约、安全边界至少另一成员review。CODEOWNERS里负责人只是默认守门人，不自动赋予队友权限；实际账号由负责人邀请并配置。
一次PR只解决一个可验收问题；不要把格式化全仓库与业务改动混在一起。
