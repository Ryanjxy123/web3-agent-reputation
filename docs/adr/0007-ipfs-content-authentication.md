# ADR-0007：链上 CID 到交付文件的内容验证

日期：2026-10-18。状态：已实施；两份真实原件及六项失败控制已离线通过，退出 0，结果见 STATUS。

Olas 链上事件记录的是 UnixFS 目录根摘要，不能将下载文件的 SHA256 与目录 CID 直接比较。本阶段复用已经取得的输入、输出和链事件，按 IPFS 官方 [trustless gateway](https://specs.ipfs.tech/http-gateways/trustless-gateway/)、[CARv1](https://ipld.io/specs/transport/car/carv1/) 与 [UnixFS](https://specs.ipfs.tech/unixfs/) 格式取得路径证明。

纯 `core.ipfs.verify_car_file` 不请求网络、不读文件。支持本次实际格式：CARv1、CIDv0/v1 的 SHA2-256、DAG-PB 普通目录、UnixFS 文件与 raw 块。逐块校验摘要，必须从已核链的预期目录根找到唯一文件名，再按链接和文件大小重组出与保留 JSON 完全相同的字节。CAR header 的 root 可以是目录或终点文件，不能代替预期链根。未知编码、缺块、歧义路径或不一致均拒绝；调用方应展示无法验证，不擅自判 Agent 失败。

文件重建在拼接前检查累计大小，最大 1 MiB、递归深度 16，避免小证明通过重复链接放大内存。当前没有声称支持所有 UnixFS/IPLD 编码。HTTP 采集仍走 SafeHttpClient，默认关闭、固定路径、显式代理、无自动重试；验证不信任网关对文件字节的声明。

这是增量证据核验，不改变已有历史增仓政策、Schema 或已发布报告。CID 通过只能说明文件与链上摘要对应，不能代替历史执行者授权、请求接手窗口、注册先后或预测结果准确性的核验。必要正常/失败验证一次复用本机两份真实 CAR，拒绝篡改块、错误路径和不同文件字节；无新增业务调用。
