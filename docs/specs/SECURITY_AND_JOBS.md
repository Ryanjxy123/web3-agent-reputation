# 安全执行、任务恢复与操作边界

## 1. 授权默认拒绝
公开注册不是测试授权。添加候选、读取公开身份、被允许获取注册URI、主动调用Agent、执行写入、发布报告分别管理。
只有Operator可创建评估/确认映射/授权；Evaluator signer只负责报告摘要发布。普通访客只能读已公开脱敏材料，不能触发外网访问或链交易。
访问grant绑定当前snapshot、能力、端点/method/path、执行链/合约、有效期、并发/频率/样本上限和授权依据。
每次实际请求前重新验证grant未撤销/过期；无凭证不探测猜密码；外部收费/认证墙停止并记AUTH_REQUIRED。

## 2. SafeHttpClient必须是唯一出口
M1只启用显式受控本地服务。M3安全门槛通过后才允许公网URI/Agent Card/8004scan服务访问。
设计参照OWASP SSRF防护，但以下具体限额是项目选择。[S06]
公网默认HTTPS、端口443、精确域名与批准path；禁止userinfo、file/gopher/ftp等协议、控制字符、混淆IP文字。
默认不跟重定向；确需redirect必须逐跳重新授权、DNS与目标检查，并限制次数，不转发凭证到新origin。
解析所有A/AAAA地址，拒绝loopback/private/link-local/multicast/reserved/非global及IPv4-mapped IPv6旁路。域名allowlist不意味着允许其解析到内网。
**必须在建连层解决DNS重绑定**：域名验证后，连接已验证的具体IP，同时保持原域名TLS SNI、证书主机校验和Host。禁止“预先resolve一次，然后普通httpx再resolve一次”的假防护。
可实现经测试的httpcore AsyncNetworkBackend/受信出口代理；不允许verify=False；连接复用只能用于同授权origin。测试覆盖二次解析变更和IPv6。
httpx默认trust_env=False，不能继承宿主代理绕过；可配置代理必须是受信固定配置，不能由Agent/请求输入提供。
系统可信RPC与不可信Agent HTTP分离：RPC endpoint由负责人配置，启动时核对chainId/code/instance，禁接收用户任意RPC URL。

本地demo不能全局ALLOW_PRIVATE_IPS=true。单独target_class=controlled_demo，只允许本次Compose注册的fixture服务名/端口/网络身份；不允许因此访问localhost其他端口、DB、云metadata或Docker API。
不可信metadata嵌套URL/图片/schema/$ref/响应statusURL都不得绕过统一出口；前端不自动加载远程图片。
data URI只接受application/json（受限UTF8或严格base64），解码后<=1MiB、depth<=32；拒绝gzip炸弹/超深结构/重复key。
ipfs URI只经显式受信gateway，校验CID与path，重新受出口限制；不递归抓任意链接。未知scheme仅标不支持。

## 3. 初始资源限额
单响应解压后<=1MiB，JSON depth<=32；连接超时5秒、单HTTP调用总截止15秒；任务业务完成窗口60秒；HTTP调用截止与任务执行窗口不要混用。
每Agent并发1；本地间隔默认1秒；公共发现保守<=10请求/分钟、单轮最多3候选；严格服从更低服务配额/Retry-After，绝不轮换账号绕限。
规则样本总量上限在suite中固定；worker全局并发初始2；单run最大slots=100（20+30+10=60，留有限余量）；不能被外部描述生成无限任务。
证据包上传压缩大小<=25MiB，解压总量<=100MiB、文件数<=1000；单文件另限10MiB，解包计数按实际流，不只相信ZIP header。
原始证据路径由系统生成且只在专用目录；压缩包不执行脚本，任何shell/SQL/工具名均不从响应文字执行。

## 4. Jobs：至少一次领取，不谎称恰好一次外部调用
PostgreSQL选取可运行job使用短事务 `SELECT ... FOR UPDATE SKIP LOCKED`，更新lease_until、lease_token(单调fencing值)、owner，然后立刻commit。锁语义参考PostgreSQL官方文档；具体租约逻辑是项目实现。[S09]
建议lease30秒、heartbeat10秒。heartbeat独立于阻塞HTTP/链轮询；所有进度与完成UPDATE都带job_id+lease_token条件。
旧worker token过期后不得提交新状态；DB返回0行即停止执行后续步骤。不在持锁事务中等待HTTP/RPC。
限制attempts，指数退避仅重试可恢复平台错误；不可恢复Schema/授权不做无限重试。

## 5. 写入发送日志与恢复决策
发送前同事务写入冻结request_id、payload_hash、expected facts、grant_id、任务截止、purpose、初始dispatch_state；随机输入也先落库。进程崩溃不能重生一个不同request_id。
NOT_SENT→在验证租约/grant后CAS置SENDING→调用Agent→保存ACKNOWLEDGED及task handle→轮询/链核验→SETTLED。
SENDING进程崩溃或网络无法确认是否送达→DISPATCH_UNCERTAIN，不能直接当NOT_SENT重发。

| 恢复看到什么 | 动作 |
|---|---|
| NOT_SENT且无发送记录 | 在新租约下正常发送 |
| ACKNOWLEDGED/已有txHash | 查Agent状态及独立RPC，继续同slot核验 |
| DISPATCH_UNCERTAIN | 先GET固定任务状态；再按executor/requestId查本地record/event |
| Agent已接受、链已有匹配记录 | 追加证据，完成原slot，不创建新任务 |
| Agent确认没有接受，且适配器保证持久幂等 | 同id同payload最多受限重投，保留原attempt |
| 不支持任务查询/幂等，链也不能确定 | UNKNOWN + DISPATCH_UNCERTAIN，人工处理或下一次新run，禁止盲写 |
| deadline已过，期间平台观测不健康 | UNKNOWN，不能判Agent超时失败 |
| 已接受且健康观测覆盖窗口，超时未完成 | ACCEPTED_TASK_DEADLINE_EXCEEDED |

即使有fencing，旧worker可能已在网络边界开始发送；不能只靠DB租约保证外部恰好一次。受控Agent持久幂等与合约唯一键必须共同生效。
受控Agent ledger使用独立SQLite或受限文件事务均可，不能依赖平台私有数据库；SQLite这里仅用于fixture服务的任务账本，不替代PostgreSQL队列并发验收。

## 6. 只读重试、取消与报告固定
只读可有限重试，但所有attempt保留。可用性按初始槽位，功能/行为轮询以固定deadline状态判定；成功重试不能变成额外独立样本。
取消只停止未发送slots；已广播或状态不明任务继续安全reconcile，禁止承诺撤销链交易。
run/reports分离：一个run可先产生partial report，后续完整数据产生新revision，不覆写旧hash。
证据采集失败仍须生成可解释部分结果；评分代码崩溃是平台错误，不能用零分兜底。

## 7. Secrets、日志与资源隔离
.env/本地secret文件加入Git忽略；前端禁止VITE_前缀装私钥/API Key；日志过滤Authorization/Cookie/x-api-key/tokens/private_key以及URL敏感query。
部署admin、evaluator、fixture executors分开；仅测试链资助。只对可信本地RPC开放开发调试方法，不向外部用户暴露anvil_setBalance等。
本地seed可以使用Anvil默认账户，但必须显著标“众所周知、不安全、仅限此demo”，且网络配置不允许这些key指向外链。公网shared-test配置必须独立凭证。
不挂Docker socket、SSH目录、用户HOME全盘；容器非root运行，写入目录显式限定；依赖安装只在用户授权的构建环境中执行。
把外部文本当数据；LLM扩展只生成受Schema约束候选，不能授权工具/改变policy/执行URL。不得把提示注入文本复制进AGENTS。

## 8. 必须的故障注入验收
两个worker抢同job；lease到期旧worker写回；发送前/发送后落ACK前退出；fixture签完tx后退出；RPC暂停；重复按钮；撤销grant；chain reset；evidence临时文件写坏；anchor广播超时；两个report并发发布。
验证没有重复业务记录、没有丢失原失败、没有误将UNKNOWN记FAIL、没有虚构已确认上链。相关日志必须可追踪run/slot/attempt/job但不带secret。
