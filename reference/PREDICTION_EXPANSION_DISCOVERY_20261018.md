# 预测扩量的有限公共调查（2026-10-18）

本轮只为既有 `prediction-history-v1` 寻找新来源，不新增类别，不改变截止时间1790812800或14个不同已结算市场、互斥7+7门槛。**没有确认新的可评分对象**；有预测声明不等于有完整历史。原池2135/2150/2267资格不足是本轮调查的触发背景，不因此修改规则或猜测市场。

调查范围与全部原件：[统一结果](../runtime/olas-extra-discovery-20261018T122710Z-af08f660/discovery-summary.json)、[摘要清单](../runtime/olas-extra-discovery-20261018T122710Z-af08f660/manifest.json)。原40行目录复用，去重此前已调查25个service；其中剩余14个FixedNative仅补桥映射。只新增官方目录一页 `first:40,skip:40`；该页15个有metadata，按原序固定前8个FixedNative补登记资料，再选有明确预测声明及I/O的4个核少量历史input，未按输出或分数选择。

固定可信链100、N=48815687及其原header/链号原件复用。桥映射实读22个service，全部返回非零实际agentID；**这些不是22个完整身份PASS**。随后8个对象实读tokenURI，7份注册JSON及7份声明manifest保留（2份旧manifest按完全相同URL/摘要复用），1份注册JSON为TransportError。本轮未重读owner及Mech的serviceId/serviceRegistry/getOperator，正式自动接入必须按共用规则核验，不能从同factory推定履约或预测能力。

全部canonical均使用 `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:<实际agentID>`，完整字符串与每条桥映射原件、声明URL及SHA见统一JSON；serviceId不默认等于agentID。

| serviceId | 实际agentID | 登记/声明资料 | 历史输入结论与缺项 |
| --- | --- | --- | --- |
| 3442 | 3766 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 3447 | 3771 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 3444 | 3768 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 3441 | 3765 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 3450 | 3774 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 3449 | 3773 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 3448 | 3772 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 3243 | 3553 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 1841 | 1841 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 2915 | 3179 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 3826 | 4151 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 2670 | 2682 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 1966 | 1966 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 1983 | 1983 | 原目录没有metadata；本轮仅核桥映射，未取登记JSON/manifest，不能认定没有功能 | 真实预测声明、工具Schema和Omen输入均UNKNOWN |
| 2692 | 2706 | 通用模型转发；输入/输出含预测措辞与概率示例，未明确声明独立二元预测，不能仅凭p_yes字段纳入 | 历史未查，当前方案声明适用性UNKNOWN |
| 2675 | 2687 | 登记JSON读取TransportError；未取得声明 | 平台读取不确定，未重试 |
| 1722 | 1722 | 已登记manifest明确预测操作与输入输出Schema；名称含testing不作评分依据 | 索引一次ReadTimeout；平台读取不确定，未取得input |
| 2661 | 2673 | 已登记manifest明确二元市场预测与输入输出Schema | 索引一次ReadTimeout；平台读取不确定，未取得input |
| 3834 | 4160 | 登记文档明确二元预测；自称独立于Valory/Autonolas，署名尚未独立认证 | 固定cutoff前索引HTTP200，delivers为空；本轮没有历史线索 |
| 2266 | 2266 | 已登记manifest明确二元市场预测与输入输出Schema | 固定索引前两份input均HTTP404，公开文件缺失；未换槽 |
| 3796 | 4121 | 声明为Google SERP快照转发，不是事件预测 | 不纳当前预测调查，不发业务 |
| 2685 | 2699 | 明确股票走势预测声明，具有概率结果Schema | 历史未查；是否有明确Omen市场输入及14个已结算市场仍UNKNOWN |

## 四个历史先筛对象

每对象只查一页最新4条、固定N与原cutoff，最多取前两个不同普通请求的 `metadata.json` 及必要CAR；没有读output，没有查询市场结算或推导预测分。未遇null CID，不猜参数，不自动重试或换任务。

- **1722 / 1722、2661 / 2673：UNKNOWN，平台读取不确定。** 各一次历史索引ReadTimeout；没有取得响应，不足以说明没有历史，也不扣Agent分。
- **3834 / 4160：UNKNOWN，原cutoff前无索引线索。** HTTP200返回 `delivers=[]`。注册文档明确二元预测并自称非Valory/Autonolas运营，manifest有完整概率I/O；这不是独立提供方认证，也不能凭当前声明前推历史存在。
- **2266 / 2266：UNKNOWN，公开输入文件缺失。** 索引返回4条；冻结前两份input均HTTP404，未取后续任务凑数。404证明本轮指定公开文件未取得，不证明预测答案错误。

原件与各阶段清单：[桥映射](../runtime/olas-extra-discovery-20261018T122710Z-af08f660/mapping-result.json)、[登记与声明](../runtime/olas-extra-discovery-20261018T122710Z-af08f660/documents-result.json)、[历史input](../runtime/olas-extra-discovery-20261018T122710Z-af08f660/history-input-result.json)。各来源仍保留请求JSON/URL、时间、响应或错误、原件SHA；统一manifest将旧输入与本次输入分开引用，未复制为新HTTP。

## 未查历史的实际声明与保留边界

- **service2685 / agent2699，profit_pulse**：真实注册manifest明确股票走势预测，输入为股票价格变动问题，输出Schema为序列化p_yes/p_no/confidence/info_utility。是可保留的预测资料线索；本轮未核其是否有明确Omen市场输入或14个已结算市场，不能宣称就绪，也不为它新增股票专用类别。
- **service2692 / agent2706**：工具描述为将prompt转交OpenAI；输入/输出有预测措辞与概率示例。没有据这组字段推定独立二元事件预测声明，保持适用性未知，不拿模型转发凑数。
- service2675 / agent2687登记文档读取失败，声明未知。service3796 / agent4121实际声明是Google SERP快照转发，不能冒充预测。原14个无metadata服务继续保留资料缺口；“没有metadata”不等于“没有功能”。
- 已有service3661仅有prediction工具名字、缺具体描述/Schema；3795/3798是历史概率校准，不纳入独立事件预测。新增页其余7个metadata行本轮未审文档，只能称未审线索，不能凭hash或factory列为预测候选。没有扩大页数或新类别。

## 实际执行与停止

四个实际采集命令均为 `.venv/Scripts/python.exe runtime/olas-extra-discovery-20261018T122710Z-af08f660/<脚本> --execute-public-readonly --proxy http://127.0.0.1:7897`，经已授权的escalated环境执行；默认不开执行开关不发请求。对应脚本及退出码为：

| 脚本 | 新公开请求 | exit | 含义 |
| --- | ---: | ---: | --- |
| `collect-directory.py` | 1 | 0 | 额外一页40行保留 |
| `collect-mappings.py` | 22 | 0 | 22个固定块桥映射保留 |
| `collect-documents.py` | 21（8RPC + 13资料GET） | 0 | 8个对象资料调查结束；包含1次TransportError，非全部成功 |
| `collect-history-inputs.py` | 6 | 0 | 4个对象有限调查结束；2次超时、1个空页、2份input404，不代表资格通过 |

本轮新增 **50条HTTP观测**：45次HTTP200、2次HTTP404、2次ReadTimeout、1次TransportError；其中30次是可信RPC只读。仅串行读取、显式代理、SafeHttpClient；登记资料GET使用固定公网DNS连接与TLS核验。401/402/403/429或RPC限额时停host，本轮无host-stop。新模型请求、业务任务、付费、签名、链上写入和output读取均0，工程测试NOT_RUN。

本轮已按边界停止，不再补请求或扩大范围。正式自动接入仍需共用身份核验、实际Omen输入、链上CID锚、结算和全部14任务资格；当前没有可直接宣布READY的新对象。网络超时与语义不适用、文件缺失、截止前无历史分别记录，不互相替代。


## 后续独立四对象自动资格批次（新增授权范围）

根代理随后依据用户已批准的同预测方案扩量方向，明确安排1722、2673（service2661）、2699（service2685）、2266作为下一独立有限四对象自动批次的冻结输入；本次仅离线准备、尚未提交或采集。此前一次索引ReadTimeout和前两份input404只说明初筛UNKNOWN，不能推断完整128候选范围不可用。后续仍由同一自动collector核验现有 `prediction-history-v1` 的输入语义、Omen市场与14个不同已结算市场，不改cutoff/7+7门槛，不按分数换题；2699不新增股票类别。4160的cutoff前空页原件保留，本批不重评。该新批次不是原调查run内的自动重试，原调查原件及清单全部冻结不改。

冻结候选包：[candidates.json](../runtime/prediction-expansion-candidates-20261018T124219Z-45506011/candidates.json)、[manifest.json](../runtime/prediction-expansion-candidates-20261018T124219Z-45506011/manifest.json)。包含实际canonical/agentId/serviceId/Mech、链上tokenURI及注册JSON、真实声明与I/O字段定位、官方目录factory原件SHA和逐对象初筛缺项，不含手填运行profile或伪造就绪结论。离线准备命令exit0、新外网/模型0，交由candidate_expansion在根代理明确启动后运行公共只读自动批次；当前准备本身不增加完整对象或报告数。
