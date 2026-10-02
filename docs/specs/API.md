# HTTP API 与受控 Agent 协议

此文件是待实现契约，不声称端点已存在。所有平台路径采用 `/api/v1`；这是对PRD未版本化路径的兼容性细化。

## 1. API统一约定
Content-Type为application/json，UTF-8；服务端生成追踪 `request_id`，与业务32-byte `task_request_id`不同。
写操作需要操作者认证；本地可以使用环境注入的随机 bearer operator token（恒定时间比较），不是硬编码密码。公开部署前增加真正身份体系，但P0不建设复杂用户门户。
token不放URL、不放前端构建环境、不持久化localStorage；本地演示由操作者在会话输入保存在内存。正式部署可改同源HttpOnly会话与CSRF。
同源优先；CORS仅允许明确开发origin，无通配credentials。
错误：`{error:{code,message,request_id,retryable,details}}`，details不得含stack/private path/secret。
422是输入结构错误，403是无权限，409是幂等冲突/状态冲突，413是包过大，429是平台限流，503是平台暂不可用。UNKNOWN业务结果仍以200/202返回。
列表使用cursor+limit，默认20，最大100，排序稳定 `(created_at,id)`；响应`items,next_cursor`。报告证据单独分页，不一次返回全部blob。

## 2. 平台端点
| 方法与路径 | 请求 | 响应/行为 |
|---|---|---|
| GET /health/live | 无 | 进程存活，200，不调用不可信Agent |
| GET /health/ready | 无 | DB/migrations/可信链配置状态，依赖未就绪503 |
| POST /api/v1/agents | AgentRef或受控sample_id | 201新建/200已有；候选不直接已验证 |
| GET /api/v1/agents | cursor,limit,capability,source_type,profile | 可分页列表；无跨画像总榜 |
| GET /api/v1/agents/{id} | 无 | 身份、declared/observed/verified、current snapshot、latest report refs |
| POST /api/v1/agents/{id}/refresh | expected_snapshot_hash? | 202 ingest_job_id；抓取放worker，不在API请求中执行任意URL |
| GET /api/v1/snapshots/{id} | 无 | 不可变快照、原文声明及证据引用 |
| POST /api/v1/snapshots/{id}/claims/confirm | confirmed映射、rejected/unsupported声明、reason、expected_review_version | 新review_version，冲突409；不接收score |
| POST /api/v1/snapshots/{id}/bindings/challenge | executor、endpoint_id、execution_chain_key | typed_data、nonce、deadline；EOA-only范围提示 |
| POST /api/v1/snapshots/{id}/bindings/verify | challenge_id、owner_signature、executor_signature | VERIFIED/UNKNOWN+reason与evidence；nonce单次消费 |
| POST /api/v1/access-grants | snapshot、限定端点/能力/方法/链/合约/次数/有效期、consent_ref | grant_id；审批者审计；不允许无限通配 |
| POST /api/v1/access-grants/{id}/revoke | reason | 撤权，停止后续调用，不撤回已广播交易 |
| POST /api/v1/evaluations | snapshot_id、review_version、profile、policy_version、grant_ids、suite_id | Idempotency-Key必需；202 run_id、status、status_url |
| GET /api/v1/evaluations/{run_id} | 无 | run state/stage，planned/settled/unknown，latest report ref |
| GET /api/v1/evaluations/{run_id}/slots | cursor,limit,purpose | 槽位及attempt/断言引用，原始失败不消失 |
| POST /api/v1/evaluations/{run_id}/cancel | reason | 202，停止后续任务，已发任务reconcile |
| GET /api/v1/reports/{report_id} | 无 | 固定report_core+单独当前有效性视图+anchor状态 |
| GET /api/v1/reports/{report_id}/evidence | cursor,limit | 脱敏manifest条目 |
| GET /api/v1/evidence/{evidence_id} | 无 | 受限字节，不接受客户端文件路径；Content-Disposition安全 |
| GET /api/v1/agents/{id}/reports | cursor,limit,profile,policy_hash | 历史报告 |
| POST /api/v1/reports/compare | report_ids[2..5] | 只允许同画像/规则/相近窗口；否则409 PROFILE_NOT_COMPARABLE |
| POST /api/v1/reports/{id}/anchor | 无，Idempotency-Key | 202 anchor_job_id；不能由客户端指定私钥、RPC、分数 |
| GET /api/v1/reports/{id}/bundle | 无 | zip；审计，不能包含secrets/运行日志全量 |
| POST /api/v1/verifications | multipart bundle + mode=offline/online + trusted_chain_key | 202 verification_id；受限上传/解包，RPC只能选择已有可信key |
| GET /api/v1/verifications/{id} | 无 | content/rule/anchor三项结果、业务复算项和limitations |
| POST /api/v1/discovery/import | source=8004scan、受限filters、max_candidates<=30（默认3） | 202 import_job_id；只导入候选，不自动测评 |
| GET /api/v1/jobs/{id} | 无 | job状态，仅公开必要错误，密钥信息不可见 |

接口异步统一返回job引用，不能把“接受请求”显示为“测完/上链”。前端首次可每2秒轮询，运行结束停止；不为P0引入WebSocket。

## 3. 创建评估实例
```json
{
  "snapshot_id": "<uuid>",
  "review_version": 1,
  "profile": "record-write-v1",
  "policy_version": "policy-v1",
  "grant_ids": ["<uuid>"],
  "suite_id": "m1-smoke-v1"
}
```
m1-smoke-v1不是另一套降低门槛的评分规则；它产生少量部分结果，policy-v1的门槛保持20/10/10。
同一actor+Idempotency-Key+同payload重复返回同run_id；同key不同payload返回409；并发请求靠DB唯一约束处理，不只靠Python if。
客户端不能指定任意rule class、合约地址、外部URL、评估时钟或最终统计。选择已批准的配置ID，服务器解析并冻结。

## 4. 受控 Agent HTTP v1（自定义协议，不叫完整A2A）
GET `/health` → `{status:'ok',protocol:'controlled-http-v1'}`；GET `/capabilities` →明确三能力支持范围；两者不证明业务正确。
POST `/tasks`，Header `Idempotency-Key = task_request_id`，请求：
```json
{
  "protocol": "controlled-http-v1",
  "request_id": "0x<64 lowercase hex>",
  "capability_id": "anchor_record",
  "snapshot_hash": "0x<64 lowercase hex>",
  "chain_id": "31337",
  "chain_instance_id": "0x<64 lowercase hex>",
  "target_contract": "0x<40 lowercase hex>",
  "record_hash": "0x<64 lowercase hex>",
  "deadline": "2026-10-02T10:01:00.000Z"
}
```
服务独立检查deadline、目标链/合约白名单、请求合法性；先在自己的ledger持久化接受任务，再执行。
接受返回202：`{request_id,accepted:true,task_status:'accepted',status_path:'/tasks/<request_id>'}`。
拒绝返回结构化4xx：`{request_id,accepted:false,error:{code,message}}`。功能负向用例正确拒绝记PASS；未接受不能作为行为组的“已接受失败委托”。
GET `/tasks/{request_id}` 返回accepted/running/succeeded/failed/rejected以及result。status_path必须限于已批准origin与固定模板，平台不盲跟绝对URL。
写入成功 result：`{chain_id,tx_hash,executor,record_hash}`，这些是候选声明，平台仍独立核验。
查询状态能力输入chain_id、tx_hash；输出confirmed_success/confirmed_failure/pending/unknown。不存在回执与pending不混为“失败”。
核验记录能力输入executor、record_request_id、expected_record_hash、目标合约；输出exists/hash_match，平台固定块独立查询。

## 5. Agent幂等和重启
以request_id为唯一键保存payload_hash、accepted_at、tx_nonce、signed_tx_hash、task状态、结果。
同id同payload返回旧状态；同id不同payload 409 IDEMPOTENCY_CONFLICT。进程重启不能丢ledger。
签名交易先持久化txHash/nonce和受限signed outbox再广播；不由平台替Agent签业务写入。
故障注入参数仅fixture启动配置可见，不能通过平台测试API随意传入“我要你成功”指令。任务处理执行真实RPC，不写死最终分数。

## 6. 页面契约
列表区分来源/画像/状态；详情区分声明与验证；进度页显示阶段与未知原因；报告页优先呈现适用范围、关键冲突和证据；历史页区分旧版本；复核页分列三项验证。
current_validity是查询时派生视图，不能写回已哈希的report_core。过期报告仍显示当时结果，加“当前需复测”提示。
前端只展示escaped文本，不直接渲染外部HTML/Markdown嵌入脚本，不自动加载任意image/iframe。
开发样例明确synthetic_example=true；完成联调后端到端验收禁止mock service替代真实API。
