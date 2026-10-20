# v054：Verified 全500题镜像身份与环境准备

本说明记录 2026-10-20 的实际准备工作，不是模型评测结果。阶段快照截至 **23:05:44 CST**：官方500项镜像身份已经固定；国内1ms的494项当前tag与官方一致，另6项因限流未知；本地完整blob为9个、314,736,932 bytes，另有正在传输的部分文件；**已加载的Verified镜像为0，实际容器预检和模型调用均为0**。因此不能把“题单与官方身份齐全”写成“500个运行环境全部就绪”。

不可变身份表为 [official-image-pins.json](../../artifacts/software-benchmark-v054/images/official-image-pins.json)，SHA256 `84f38ce2aca19b7f0c366bdae04dffeb314cb097892ac94b8650a181e692c8cb`，1,538,483 bytes。它包含全部500题的仓库、基准commit、原始镜像名、top/selected manifest、config和每层的digest/size，以及官方CI的commit、运行号和8个artifact摘要。该文件没有隐藏补丁、评分脚本或镜像层内容，独立于后台持续更新的运行状态。

阶段数字保存在 [preparation-stage-snapshot.json](../../artifacts/software-benchmark-v054/images/preparation-stage-snapshot.json)。后台状态可能随后推进；本文不把未来定时器、等待服务或计划中的CPU控制写成已完成。

## 官方当前版本身份

全500题来自既定数据revision `78f471bf655a3137b2e8a75af1501690ec009ec3`，没有按镜像可达性改变题目或缩小分母。输入为 `config/v054-verified-image-inventory.json`，SHA256 `ca5ceb9a0b9e9cfc491d59b4c060406f39236815ab3e2ff5d83805636bc72e67`。

宿主对官方认证入口的一次直连检查在30秒后未取得可用响应；没有使用代理或读取镜像层。随后 [GitHub Actions 39437579123](https://github.com/haoyueliuzhao/ProWorkSim/actions/runs/39437579123) 在固定提交 `b49e1400c8226129689ece07e3b2c343585484fe` 上分8个shard查询官方registry。500项均取得成功结果，每份manifest正文与registry摘要一致；多平台索引仅选择唯一linux/amd64项。

8个artifact以GitHub提供的摘要核对后下载到：

```text
runs/software-benchmark-v054/images/official-ci-39437579123/
```

每个shard保留原始top/selected manifest、响应头和逐题结果。`transfer-receipt.json`保留artifact来源和摘要。官方身份仅表示本次查询时的当前tag内容；实际运行将绑定不可变digest/config ID，不随以后latest变化。

全500题按digest去重后，共 **1,195个blob（含config），131,932,243,128 bytes**。这是压缩资产总量，不是500个镜像简单相加，也不是展开后的Docker磁盘占用。manifest没有给出可靠的展开后磁盘总量，因此该字段保持null，使用实际剩余空间门控制加载。

## 1ms来源与真实限流

使用显式禁代理、禁止自动跳转的metadata客户端，从 `docker.1ms.run` 完成500项查询：494项top/selected/config/层描述与官方一致，以下6项保留unknown：

```text
sympy__sympy-24066
sympy__sympy-24213
sympy__sympy-24443
sympy__sympy-24539
sympy__sympy-24562
sympy__sympy-24661
```

这些失败不是模型失败，也没有用于换题。6个镜像的官方不可变身份已由CI取得，因此仍可按官方digest请求blob，最终通过完整SHA和config ID验证交付；不能因此将其镜像站latest查询记成成功。

首题固定为UTF8排序的 `astropy__astropy-12907`。首个辅助脚本曾因项目路径计算错误在导入时退出；它没有进入网络、Docker或模型操作，原错误记录保留。路径修正后开始实际下载。22:22，420,167,964-byte公共层在registry入口遭遇429，payload为0；其它已在途连接继续保存实际字节。原控制进程等待这些线程结束，不代表缺失层已经恢复，也没有运行旧版CPU预检。

22:40，新的全量准备服务在164-byte缺层的registry入口再次收到429并停止排队任务。随后只进行一次最大4KiB的错误响应诊断，实际读取17 bytes，得到：

| 字段 | 实际响应 |
| --- | --- |
| HTTP状态 | 429 |
| Retry-After | 3600秒 |
| RateLimit-Limit | `1000;w=3600` |
| RateLimit-Remaining | `0;w=3600` |
| 响应Date | 2026-10-20 14:43:50 GMT，即22:43:50 CST |

因此冷却前不继续探测1ms。现有成功manifest、完整blob和partial全部保留，不重跑494项metadata。上述429发生在registry入口，不是推测的CDN签名过期。

## APIBA替代来源

用户进一步要求尝试其它国内镜像后，主代理验证 `docker.apiba.cn`：

- 标准同域Bearer认证可用，整个流程统一使用 `ProWorkSim-source-preparation/0.54` User-Agent。
- 代表首题的top、selected linux/amd64 manifest和4,210-byte config均与官方摘要一致。
- 对420MB层请求`Range: bytes=0-4095`时，服务返回HTTP200及完整对象的Content-Length，实际仅读取4,096 bytes后关闭。**这没有证明Range可用，不能用它续传或分段。**
- 没有跳转原站或使用宿主代理。所见CF-Ray标记为FRA，不能宣称全部数据交付链路位于中国大陆。

新增 `tools/verified_apiba_blob_v054.py` 仅允许精确域名 `docker.apiba.cn`，禁止所有重定向、代理、自动重试和原站回退，只接受完整HTTP200流。若已有非空partial，直接保留并拒绝重新下载；成功必须满足原始官方大小和完整SHA256。

`proworksim-v054-apiba-first-layer.service` 正在下载首题原先payload为0的420MB缺层，与主准备器共用目标路径、文件锁和完成回执。23:05:44快照中该partial为50,331,648 bytes，**尚未完成完整SHA，不能计作可靠整层交付已经通过**。

`proworksim-v054-apiba-prefetch.service` 当前只等待上述完整SHA。只有该大层完整通过后，才以最多4连接正式获取其它完全缺失的blob；按固定题序首次使用顺序调度，跳过活动传输、已有完整缓存和非空partial。该接续不会因为小config成功就声称所有镜像可交付，也不为测速额外请求大文件。

替代来源证据位于：

```text
runs/software-benchmark-v054/images/alternative-domestic-r5/
runs/software-benchmark-v054/images/apiba-prefetch-r1/state.json
```

## 传输、加载与CPU检查实现

主入口为 `tools/verified_image_prepare_v054.py`：

1. 只接受全500题官方身份；镜像站已成功结果若与官方不同立即拒绝，unknown单列。
2. 共享blob按digest去重。旧v053完整层只在摘要回执和文件device/inode/size/mtime/ctime一致时复用，不重复hash已验证大层。
3. 对1ms新大层使用 `tools/verified_registry_ranges_v054.py`：每blob一次认证和交付URL解析，URL/token只在内存，跨域不转发Bearer。共享CDN池分段读取，必须精确HTTP206、Content-Range和大小，最后组装时一次完整SHA。
4. 完整段及未完成段的已有字节都可保留；签名失效、429、区间不符或SHA错误暂停，不自动换源、换版本或循环重试。已完成blob继续使用原始SHA回执。
5. 每个blob的新registry入口至少间隔8秒，为观测到的小时额度保留余量。准备器使用固定题序的首次使用顺序，使完整镜像能够较早就绪。
6. 仅连接专用Docker socket `runs/software-panel-v053/docker/docker.sock`，不改共享daemon或代理。标准Docker archive以流式方式交给`docker load`，不额外保存一份大型archive，也不直接操作Docker存储目录。
7. 每镜像以实际config/image ID和linux/amd64身份核对。完整依赖就绪的镜像可在其它blob仍下载时加载和CPU检查。
8. 数据和缓存仅在`/data0`下，保留至少200GiB空闲；加载前再次核对空间。没有删除旧资产或用户数据。

未开始的1ms续传配置已经调整为 **24个CDN连接 + APIBA最多4连接 + 原先最多4个在途连接，总上界32**。这只调整新进程，没有重开或中断原连接。

CPU预检使用独立、无网络、只读容器，不请求GPU，不运行答案补丁或隐藏评分。检查实际HEAD、tree、工作树clean状态、所有refs的未来commit、reflog中的未来commit，以及无引用commit是否超出基准祖先；另检查指定Conda缓存、base环境和额外环境中的目标包副本路径。工作树不clean、未来历史或目标源码副本都需要明确处理，不静默放行。

这些检查针对已知通道，不是全文件系统无泄露证明。最终actor隔离、完整依赖/评分合同及官方评分CPU接缝仍是独立条件，不能把本预检通过直接等同于所有求解环境和评分均完成。

## 持久接续与实际状态

| 单元 | 当前作用 |
| --- | --- |
| `proworksim-v054-image-preparation.service` | 原全量尝试因429停止；失败证据保留 |
| `proworksim-v054-image-preparation-r2.timer` | 单次计划于2026-10-20 23:44:00 CST启动24连接的冷却后续传 |
| `proworksim-v054-apiba-first-layer.service` | 实际传输首题缺失420MB层；完成SHA待定 |
| `proworksim-v054-apiba-prefetch.service` | 等待API大层完整证明，再有界获取其它缺失完整blob |
| `proworksim-v054-first-image-ready.service` | 每30秒仅检查首题11个blob的完成回执和stat；齐后执行无网络的本地load/preflight |

旧 `proworksim-v054-image-resume.timer` 已由r2替代并停止，旧回执保留。新冷却timer只运行一次；再次限流仍暂停，不形成重试洪泛。

首题就绪hook会保留完整500行库存，原子写入该题loaded状态，供独立的 `proworksim-v054-scorer-preflight-r2.service` 执行一次已授权官方CPU评分接缝。该等待与评分不启动模型、不生成候选、不反馈隐藏结果给Agent，也不改写旧首控制失败记录。

主要运行证据：

```text
runs/software-benchmark-v054/images/preparation-r1/image-inventory.json
runs/software-benchmark-v054/images/preparation-r1/blob-proofs.json
runs/software-benchmark-v054/images/preparation-r1/blobs/*.blob.verified.json
runs/software-benchmark-v054/images/preparation-r1/blobs/*.blob.ranges/ledger.json
runs/software-benchmark-v054/images/preparation-r1/preflight/*.json
runs/software-benchmark-v054/images/preparation-r1/first-ready-watcher.json
runs/software-benchmark-v054/images/registry-429-diagnostic.json
```

## 必要控制与解释范围

本次共有10个不同合成CPU控制通过：metadata正文身份与拒绝篡改2项、全500计划的跨源不一致拒绝及unknown保留2项、镜像依赖一齐即可加载的流水线1项、严格Range及不中断/断点/凭证边界3项、APIBA完整流与缓存/partial保护及禁止跳转2项。只对有实际改动的计划控制做了必要复核，没有重跑旧实验、旧17项文件接口控制或真实模型测试。限定Ruff已通过；首次发现的就绪watcher未使用import已修正并仅复查该文件。

源站限流、连接慢和未完成镜像是准备状态；它们没有被记为模型失败。当前没有完整500环境完成声明，没有新增正式评测授权，也没有训练或GPU占位。
