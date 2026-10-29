# Universal Router原子兑换解析范围

2026-10-28 UTC调查，延续至本地2026-10-29。实现仅为离线协议解析与独立意图绑定，不含Agent评分、来源报告适配、钱包、RPC、当前时间或数据库。旧`unsigned_swap_protocol.py`保持不动。

## 实际协议来源

真实7call原件为 `runtime/candidate-expansion-goal-20261028-direct/phase3/topaz-base-build.response.bin`，测试fixture仅提取其完整调用序列、声明输入与来源SHA，不制造已执行交易。Router为Base `0xe4b23F13b24232C1E68AD0575191216152AA9480`，该地址只存在于真实fixture/调查说明；解析器不按Agent名、域名或地址分支。

本轮GET取得[BaseScan验证源码与ABI](https://basescan.org/address/0xe4b23F13b24232C1E68AD0575191216152AA9480)，保存完整2,718,235字节页。安全客户端2MiB限额首次截断后，预先列明同一源文档的新8MiB界限再GET，原截断观测保留。抽取61个公开源码文件与ABI；10个关键文件与[官方仓库固定提交6066563](https://github.com/topazdex/universal/tree/60665630271bf2d387853d9559b6ce82adf43245)逐字匹配（仅统一CRLF/LF）。没有编译、RPC bytecode比较或确认部署与构造参数：这部分由负责人追加可信固定块证明。

公开原件与比较记录：`runtime/protocol-universal-router-20261028/verified/{compiler-input.json,abi.json,source-review.json}`。`compiler-input.json`是浏览器公开editor的language/sources投影，不冒称包含可复现编译所需的完整settings。

该实现是Velodrome/Slipstream方言，不能按Uniswap名称套池规则：

- `execute(bytes,bytes[],uint256)`、commands00/04分别为V3_SWAP_EXACT_IN/SWEEP。[入口](https://github.com/topazdex/universal/blob/60665630271bf2d387853d9559b6ce82adf43245/packages/universal-router/contracts/UniversalRouter.sol)、[分派](https://github.com/topazdex/universal/blob/60665630271bf2d387853d9559b6ce82adf43245/packages/universal-router/contracts/base/Dispatcher.sol)
- V3路径为20字节资产+3字节**int24 tickSpacing**+20字节资产；多跳继续追加23字节，CL池由factory、实现合约及排序资产/tickSpacing的salt推导ERC1167 clone。[V3执行](https://github.com/topazdex/universal/blob/60665630271bf2d387853d9559b6ce82adf43245/packages/universal-router/contracts/modules/topaz/v3/V3SwapRouter.sol)、[路径](https://github.com/topazdex/universal/blob/60665630271bf2d387853d9559b6ce82adf43245/packages/universal-router/contracts/modules/topaz/v3/V3Path.sol)
- SWEEP输入ABI虽为uint256槽，实际Dispatcher的`amountMin`局部变量是uint160；高位将截断。解析器拒绝超出160位的最低值，不能将原高位值当执行门槛。
- payerIsUser取原子执行者`lockedBy`，内部recipient允许明确router或ADDRESS_THIS；不把SWEEP里的MSG_SENDER占位符误当一个外部地址。[执行者锁与映射](https://github.com/topazdex/universal/blob/60665630271bf2d387853d9559b6ce82adf43245/packages/universal-router/contracts/base/LockAndMsgSender.sol)
- Permit2使用`approve(address token,address spender,uint160 amount,uint48 expiration)`；不包含permit签名。[Permit2接口](https://github.com/Uniswap/permit2/blob/main/src/interfaces/IAllowanceTransfer.sol)

## 接口与确定性事实

新模块 `services/platform/src/reputation_platform/atomic_swap_protocol.py`：

```python
normalize_atomic_swap({"chain_id": 8453, "calls": [...]}, quote_deadline=None)
verify_atomic_swap_intent(plan, expected, quote_deadline=None)
```

`expected`五个必需字段与既有unsigned协议一致：token_in、token_out、amount_in、recipient、minimum_out。可额外绑定独立router、permit2、executor、chain_id、deadline；不从提供方自报PASS或分数取值。金额/时戳为精确整数，quote_deadline接受整数或整数串，调用方须先将ISO时间标准化。没有获取当前时间；只计算execute deadline、Permit2 expiration与已给quote_deadline的最早值，由固定块timestamp证据判是否在窗内。

返回协议标签`universal-router-slipstream-v3-atomic-v1`，以及router/permit2/spender、资产/精确数量/收款者/最低值、完整规范化call列表与CALL类型、commands、路径各跳tickSpacing、授权与零清理、deadline、call_sequence_hash和必要状态查询说明。完整hash对chain_id与规范化7call确定性编码后keccak，不包含自身链交易哈希、当前时间、评分或Agent身份。

只完成意图比较时才添加calldata_binding_verified=true。deployment/simulation/execution/atomic_execution/pool_binding/recipient_balance_delta/fee_state仍全部false；解析器不把ABI可解析冒充实际部署可信、原子执行成功或业务结果通过。

## 七调用边界

严格接受7个有明确to/data/value的普通CALL，顺序为：

1. tokenIn approve(router,0)，清旧direct-router授权。
2. tokenIn approve(Permit2,0)。
3. tokenIn approve(Permit2,amountIn)，要求精确正值且不超过uint160。
4. Permit2 approve(tokenIn,router,amountIn,expiration)，正expiration、uint48规范宽度。
5. router execute，只有无flag的commands0004与两个输入。V3 exact-in必须payerIsUser=true、输出暂留router、路径输入/输出匹配，正有界amountIn；SWEEP必须同一tokenOut、明确外部recipient、正uint160 minimum。
6. Permit2 approve(tokenIn,router,0,expiration)，清同一授权；amount=0是清理条件，expiration如实保留。
7. tokenIn approve(Permit2,0)。

每call value必须0；to角色、所有approval spender/token/amount与输入相符；若提供from或chainId/chain_id，必须匹配要求的执行者/链。带operation/delegatecall等未支持执行属性、额外调用、只发送swap、缺清理均拒绝。ABI偏移必须规范且连续，固定参数长度严格，拒绝重叠输入、尾随字节、非零padding、非规范bool或地址高位，防止解析事实与实际命令读取不一致。

ALLOW_REVERT及保留flag、permit/permitBatch、子计划、其他命令、任意transfer/native wrap/unwrap、NFT/mint/deploy均不在范围；模块返回拒绝而非“未知opaque但允许发出”。不支持的合法协议形状由接入层保留未适配，不自动扣Agent分。初版仅支持本已核方言和完整7call；不同UniversalRouter fork不得只凭相同selector复用部署许可。

## 最低到账与池证明的关键限制

SWEEP检查**Router转出前的tokenOut总余额**达到minimum，然后转出全部余额；它没有比较收款者转前/转后差额。真实原件的V3内部minimum=0，最终SWEEP最低42702607642243；这不能自动证明该数额全部由本次swap产生，也不排除转账税等影响。[实际Payments实现](https://github.com/topazdex/universal/blob/60665630271bf2d387853d9559b6ce82adf43245/packages/universal-router/contracts/modules/Payments.sol)

因此facts明确minimum_out_check=`router-total-token-balance-before-sweep`、requires_router_output_balance_accounting=true、recipient_balance_delta_verified=false。负责人须证明Router原tokenOut余额为0或独立核算扣除旧余额，核真实收款净增≥minimum、输入净减、事件和完整原子回执；否则保留缺项。不能只凭SWEEP命令给B通过。

required_state_reads提供token→Permit2、token→router、Permit2(owner,token,router)的前后allowance及用户/Router的tokenIn/tokenOut前后balanceOf；三类授权最终量要求0。Permit2输出expiration/nonce字段如实记录，未声称nonce清零。

Router验证ABI没有公开factory/Permit2 getters，仅execute重载、stf和callback。required_deployment_bindings明确需要可信验证源码/构造参数/immutable证明，将Permit2、CLFactory和CLImplementation绑定至该部署；不虚构`router.factory()`。每跳再要求已绑定CLFactory的`getPool(address,address,int24)`、池token0/token1/tickSpacing及ERC1167 implementation核对；这些地址在离线解析时尚未知，不能使用提供方元数据里的任意factory/RPC。池费用和流动性仍需固定块真实状态。

## 验证与交付

仅运行一个必要测试方法：真实7call fixture的正常绑定、独立5字段/附加绑定不符、精确授权/清理、收款、payer、链/原生值、flag/permit命令、SWEEP uint160截断、非规范ABI/重叠/尾随、仅swap/额外mint/deploy调用及较早expiry负控。合成篡改仅为工程负控，不计真实任务或Agent失败。将全部router引用重定位仍可解析，但deployment_verified仍false，以证明协议解析不写死对象/地址。

实际命令 `.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_atomic_swap_protocol.py -v`，1测试/0.009s/exit0；收据 `runtime/protocol-universal-router-20261028/test-receipt.json`。仅运行此一次定向工程测试，旧suite、RPC/链模拟/钱包/真实执行均NOT_RUN。

源码阶段共17个公开GET、0业务API、0RPC、0钱包/签名/付款/广播；16完整200，1个200因2MiB上限保留截断观测。初始含URL片段的计划被SafeHttpClient在任何网络动作前拒绝（exit1），新计划去掉片段后读取；未放松URL/目的地检查。离线源码提取先后因网页JS终止符、反引号转义、editor无settings字段失败，修正静态解析后exit0；没有执行网页代码或丢弃原页。用户及负责人保持禁止发币、身份/报告mint、新部署红线；本模块不新增任何执行入口。旧评分与报告不变，由负责人将协议范围并入本轮ADR/状态和后续通用来源适配。
