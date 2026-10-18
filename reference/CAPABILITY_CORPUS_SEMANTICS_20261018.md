# 目录功能声明语义映射（2026-10-18）

本轮对106种目录业务原文作 **Codex逐项语义审阅**，不是人工专家认证，也没有新增DeepSeek或其他外部模型API请求。输入来自已保留公开登记资料，未联网、调用业务、启动评价、编写第三类或运行工程测试。

完整可核对结果见 [configs/corpus-semantic-review-20261018.json](../configs/corpus-semantic-review-20261018.json)。每条绑定原文SHA、连续引文、原始响应SHA与JSON Pointer，以及全部完整注册身份。共272个索引身份、173个身份有本轮可计的当前具体动作声明；这两个数都不是可测对象数。

## 覆盖口径

D表示不同完整注册身份的当前肯定动作声明数。明确inactive、只写过去或未来计划，以及只给交易角色而未展开动作者不计当前D。未发现inactive标记也不证明服务在线；当前D是文字层面声明，不是行为结论。M需要完整接口、权限、判据及任务与交易关联，本轮保持未知。提供方继续UNKNOWN。跨链版本、模板和同owner不能冒充独立提供方。

| 动作簇 | 声明覆盖 D | 去重原文数 | 可测 M |
| --- | ---: | ---: | --- |
| read_query · 读取与查询 | 28 | 21 | 未核实 |
| derive_forecast · 未来预测 | 2 | 2 | 未核实 |
| calculate_plan · 计算、分析与规划 | 90 | 38 | 未核实 |
| execute_write · 执行与写入 | 39 | 20 | 未核实 |
| monitor_alert · 监控与警报 | 32 | 30 | 未核实 |
| research_content_code · 研究、内容与代码 | 28 | 15 | 未核实 |
| verify_attest · 核验与证明 | 13 | 8 | 未核实 |
| other · 其他明确服务或未展开角色 | 19 | 14 | 未核实 |

一份原文或一个Agent可属于多簇，因此各行D不能相加。动作簇用于调查，不把同簇不同判据合成一个评价方案。

## 必须保留的语义边界

- Zyfai原文只说寻找收益机会，不能按名称“Rebalancer”认定执行再平衡。Swap Executor只说寻找路径，也不认定执行兑换。
- Omen/Polymarket“Trader”角色不自动等于概率预测或已签名交易；下注动作有明确placing bets原文时才标写。
- 盘口概率、概率趋势、资金流资料、历史回测及投资建议不作为未来事件概率。网络拥堵和资金费率是两类明确的未来状态/数值预测，仍未给概率结构；本106原文没有明确未来事件概率输出。
- 收费服务、x402、持币资格和策略条件按原文保留，不当作匿名免费可调用。
- 社交点赞/转发是站外动作；NFT图像更新、锚定和未说明场所的交易另标状态范围，不能当成已证实链上履约。
- 黄金资料Agent明确不执行交易；单靠Bitcoin名称会猜错业务。

6个原件明确metadata.active=false的身份不计当前D：137/374, 42161/13, 42220/15, 42220/19, 42220/4, 56/28。137/3只描述过去工作与未来计划，也不计当前动作。

## 资料与Schema缺项

每条JSON都记录schema_status与缺项。Celo #7有部分真实工具参数与返回字段，仍未覆盖描述中的全部能力；其余条目未在本语义审核中建立覆盖全部动作的Schema。不能把MCP或网页地址当作完整业务规范。已有149条来源核验声明由另一份库存按canonical合并，不被本轮目录缺项覆盖。

新增详情还保留17段独特结构化业务原文，来自Celo #7与#17：skills.description 10段、tools.description 7段。它们尚未逐条纳入这106描述映射，逐段SHA与来源列于JSON的unmapped_structured_material；不声称17项新能力。capabilities中的标签和布尔开关不算具体业务原文。本轮不为穷尽继续扩写。

## 106项审阅索引

表内只列调查动作；完整连续引文、否定/条件、时间状态和canonical身份关系以JSON为准。

| 项 | 原文SHA前12位 | 登记身份数 | 可计D的身份数 | 标注动作 |
| ---: | --- | ---: | ---: | --- |
| 001 | `9cde14092a4b` | 2 | 2 | calculate_plan, read_query, research_content_code |
| 002 | `b3e88b672eea` | 48 | 48 | calculate_plan |
| 003 | `4481bdd5f5ac` | 1 | 1 | read_query |
| 004 | `38f783168b0a` | 1 | 1 | read_query, monitor_alert |
| 005 | `76df6b0beb18` | 1 | 1 | read_query, calculate_plan |
| 006 | `d7d2d81990f4` | 4 | 4 | research_content_code |
| 007 | `61933827f644` | 6 | 6 | read_query, research_content_code, verify_attest, other |
| 008 | `4a24f82aca2a` | 4 | 0 | other（不计当前D） |
| 009 | `f55a6ea2799e` | 14 | 0 | other（不计当前D） |
| 010 | `e8f909ff64a6` | 1 | 0 | other（不计当前D） |
| 011 | `c0b5c1bc4279` | 18 | 18 | execute_write |
| 012 | `bbdd97a82f07` | 1 | 1 | calculate_plan |
| 013 | `d0d8bb3401b5` | 1 | 1 | read_query, calculate_plan |
| 014 | `2487e96bb03d` | 1 | 1 | read_query, calculate_plan |
| 015 | `982c342ed81a` | 1 | 1 | calculate_plan |
| 016 | `14d1fe317812` | 1 | 1 | execute_write |
| 017 | `70a1de61620f` | 1 | 1 | monitor_alert, calculate_plan, execute_write |
| 018 | `4df1a3199e9c` | 41 | 0 | other（不计当前D） |
| 019 | `ca8e960e9c78` | 1 | 0 | calculate_plan（不计当前D）, research_content_code（不计当前D） |
| 020 | `de4e48e1af01` | 1 | 0 | monitor_alert（不计当前D）, research_content_code（不计当前D）, other（不计当前D） |
| 021 | `c553c385e1c9` | 1 | 1 | calculate_plan |
| 022 | `dfee75bafcc1` | 1 | 1 | read_query |
| 023 | `7a769af8fa13` | 1 | 0 | other（不计当前D） |
| 024 | `09c405fd0089` | 2 | 2 | calculate_plan |
| 025 | `718a9482711e` | 2 | 2 | calculate_plan |
| 026 | `f42a70bad695` | 1 | 1 | read_query, verify_attest |
| 027 | `bc3699729c46` | 1 | 1 | other（不计当前D）, read_query |
| 028 | `e8dafc53d112` | 1 | 1 | calculate_plan, read_query, research_content_code |
| 029 | `09295fe60603` | 1 | 0 | execute_write（不计当前D） |
| 030 | `9a98507de6ab` | 1 | 1 | read_query, execute_write, calculate_plan |
| 031 | `a82ac90f6e20` | 1 | 1 | derive_forecast, calculate_plan |
| 032 | `45c8d78c082a` | 1 | 1 | read_query, monitor_alert, calculate_plan |
| 033 | `308104c57530` | 1 | 1 | monitor_alert, calculate_plan |
| 034 | `4039088f9d07` | 1 | 1 | calculate_plan |
| 035 | `9c66e08dd257` | 1 | 1 | execute_write |
| 036 | `c9784e930f8c` | 1 | 1 | monitor_alert |
| 037 | `088cea9382da` | 1 | 1 | calculate_plan |
| 038 | `2be770c19632` | 1 | 1 | read_query, calculate_plan |
| 039 | `027e979c2d33` | 1 | 1 | calculate_plan |
| 040 | `64e662bd4c9a` | 1 | 1 | verify_attest |
| 041 | `c2027abc107a` | 1 | 0 | read_query（不计当前D）, calculate_plan（不计当前D）, execute_write（不计当前D） |
| 042 | `c2c7230f8071` | 1 | 1 | other |
| 043 | `f72b1d6f955d` | 1 | 1 | monitor_alert, calculate_plan, execute_write |
| 044 | `c43bf43326de` | 1 | 1 | monitor_alert, calculate_plan, execute_write |
| 045 | `f1204525cfb6` | 1 | 0 | monitor_alert（不计当前D）, execute_write（不计当前D）, calculate_plan（不计当前D）, derive_forecast（不计当前D） |
| 046 | `e4767bd13796` | 1 | 1 | other, research_content_code, verify_attest, execute_write |
| 047 | `2041d66d6ab5` | 1 | 0 | execute_write（不计当前D） |
| 048 | `e62e49fd7054` | 2 | 2 | monitor_alert, execute_write, read_query, calculate_plan |
| 049 | `566d6d4e1c33` | 1 | 1 | research_content_code, execute_write |
| 050 | `37efc1052c14` | 2 | 2 | monitor_alert, execute_write, calculate_plan |
| 051 | `ecf00169e107` | 1 | 1 | other, monitor_alert |
| 052 | `ae73dce25256` | 1 | 0 | other（不计当前D） |
| 053 | `7a21a8efd00d` | 1 | 1 | monitor_alert |
| 054 | `89c484ba999e` | 1 | 1 | calculate_plan |
| 055 | `e89764e73610` | 1 | 1 | verify_attest |
| 056 | `54179ae67259` | 1 | 1 | monitor_alert |
| 057 | `ed9c4668bac8` | 1 | 1 | monitor_alert |
| 058 | `3da7d08b1c11` | 1 | 1 | monitor_alert |
| 059 | `de5734404865` | 1 | 1 | calculate_plan |
| 060 | `3f457d47f810` | 1 | 1 | monitor_alert |
| 061 | `93a960c0ea82` | 1 | 1 | calculate_plan |
| 062 | `4e31cbbc37c8` | 1 | 1 | calculate_plan |
| 063 | `7ee4b483ebef` | 1 | 1 | calculate_plan |
| 064 | `a371cc2f665c` | 1 | 1 | monitor_alert |
| 065 | `6f4fb51e81ac` | 1 | 1 | other |
| 066 | `45b17cdcf0a7` | 1 | 1 | monitor_alert, other |
| 067 | `4f2ce3d96708` | 1 | 1 | other |
| 068 | `a4ea91f35fe8` | 1 | 1 | monitor_alert |
| 069 | `98694219c66b` | 1 | 1 | monitor_alert |
| 070 | `a1f830f7d787` | 1 | 1 | monitor_alert |
| 071 | `234b4a2b81cf` | 1 | 1 | calculate_plan |
| 072 | `7b0a988d53bf` | 1 | 1 | monitor_alert |
| 073 | `507545d22ef8` | 1 | 1 | other, monitor_alert |
| 074 | `dc0ea607b1df` | 1 | 1 | execute_write |
| 075 | `596da478fc10` | 1 | 1 | read_query, calculate_plan |
| 076 | `eda03f04494e` | 1 | 1 | calculate_plan, monitor_alert |
| 077 | `d42bbe6ad9e4` | 1 | 1 | monitor_alert, calculate_plan |
| 078 | `43948b1ac215` | 1 | 1 | monitor_alert, other（不计当前D） |
| 079 | `0be82d1ba20e` | 1 | 1 | derive_forecast, calculate_plan |
| 080 | `bda7091b6d3a` | 1 | 1 | calculate_plan, execute_write, monitor_alert |
| 081 | `3b9c9dca9c0e` | 1 | 1 | execute_write |
| 082 | `7b04496c3006` | 30 | 0 | other（不计当前D） |
| 083 | `ef208b3d5811` | 1 | 1 | calculate_plan, research_content_code |
| 084 | `52f6632c7352` | 1 | 0 | read_query（不计当前D）, calculate_plan（不计当前D）, research_content_code（不计当前D） |
| 085 | `d6229eb0316d` | 1 | 1 | read_query |
| 086 | `c564b1ea85d5` | 1 | 1 | monitor_alert |
| 087 | `6b5511c13ddb` | 1 | 1 | other |
| 088 | `4b4b026cc3ba` | 1 | 1 | execute_write |
| 089 | `8d8586a63a48` | 1 | 1 | monitor_alert |
| 090 | `cdcd34914dcd` | 1 | 1 | verify_attest, other |
| 091 | `7f6a64413a31` | 1 | 1 | calculate_plan |
| 092 | `a688147d8786` | 1 | 1 | calculate_plan, monitor_alert |
| 093 | `33ffe525729f` | 1 | 1 | verify_attest |
| 094 | `07ac8055a1c6` | 1 | 1 | other, monitor_alert |
| 095 | `0c112178cb15` | 5 | 5 | research_content_code |
| 096 | `792252891069` | 1 | 1 | research_content_code |
| 097 | `cd127e1d13f7` | 1 | 1 | research_content_code, read_query |
| 098 | `9af7758a2f8d` | 1 | 1 | research_content_code |
| 099 | `9f8aa9dfb089` | 1 | 1 | research_content_code |
| 100 | `6ddf72816b0a` | 1 | 1 | research_content_code |
| 101 | `d36a76322de7` | 1 | 1 | execute_write, research_content_code, other |
| 102 | `0f7001150b53` | 1 | 1 | execute_write |
| 103 | `aa861fa0d544` | 1 | 1 | read_query, execute_write |
| 104 | `3afe8eaeea43` | 1 | 1 | read_query, other, execute_write |
| 105 | `694c90f95b46` | 1 | 1 | execute_write |
| 106 | `d46459a7e547` | 1 | 1 | research_content_code, verify_attest, other, read_query |

来源导出校验退出0：106种原文与272个身份关系绑定到122份原始HTTP响应，核对观测、SHA、JSON Pointer和连续引文。修改过的标注在最终导出时校验，不运行工程测试。全部来源复用既有原件；没有新增网络、RPC、Agent业务或模型API调用。

本报告不选第三类、不计算声誉分，不按D大小直接决定实施价值；总排序由主任务结合不同提供方和可测证据缺项完成。
