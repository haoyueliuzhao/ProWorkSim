# v054：Verified 全500题镜像身份与环境准备

本说明记录 2026-10-20 的实际准备工作，不是模型评测结果。阶段快照截至 **23:05:44 CST**：官方500项镜像身份已经固定；国内1ms的494项当前tag与官方一致，另6项因限流未知；本地完整blob为9个、314,736,932 bytes，另有正在传输的部分文件；**已加载的Verified镜像为0，实际容器预检和模型调用均为0**。因此不能把“题单与官方身份齐全”写成“500个运行环境全部就绪”。

不可变身份表为 [official-image-pins.json](../../artifacts/software-benchmark-v054/images/official-image-pins.json)，SHA256 `84f38ce2aca19b7f0c366bdae04dffeb314cb097892ac94b8650a181e692c8cb`，1,538,483 bytes。它包含全部500题的仓库、基准commit、原始镜像名、top/selected manifest、config和每层的digest/size，以及官方CI的commit、运行号和8个artifact摘要。该文件没有隐藏补丁、评分脚本或镜像层内容，独立于后台持续更新的运行状态。

阶段数字保存在 [preparation-stage-snapshot.json](../../artifacts/software-benchmark-v054/images/preparation-stage-snapshot.json)。后台状态可能随后推进；本文不把未来定时器、等待服务或计划中的CPU控制写成已完成。

后续唯一收尾快照为 **2026-10-21 00:03:45 CST**，见 [带时间快照](../../artifacts/software-benchmark-v054/images/preparation-snapshot-20261020T160345Z.json)：25个blob通过完整SHA，合计1,569,997,505 bytes；Verified镜像loaded仍为0/500，API首层partial为330,301,440 bytes，尚未完整验SHA。主准备器发生新的读取超时并处于`pausing_public_fault`，进程等待在途操作退出；这不是429。429监督器实际active，但不会把未知网络超时伪装成有Retry-After的限流并盲目重试。API流及等待服务仍active，实际scorer仍为`waiting_for_fixed_image`，模型调用为0。所有partial/分段保留，完整环境仍未就绪。

针对这次已保存的读取超时，**00:14:26 CST** 另行启动r2监督器，增加60/300/900秒、最多3次的有界续传。旧快照没有改写，新 [控制与启动回执](../../artifacts/software-benchmark-v054/images/read-timeout-retry-control-r2.json) 单独保存。切换只停止旧监督器，主下载、API首层和API预取的进程ID均保持；新监督器仍在等待原下载进程自然退出，尚未实际发起超时恢复，不能将控制通过解释为网络恢复成功。

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
3. 对1ms新大层使用 `tools/verified_registry_ranges_v054.py`：每blob先认证并解析交付URL，URL/token只在内存，跨域不转发Bearer；明确到期的lease可按下述边界刷新。共享CDN池分段读取，必须精确HTTP206、Content-Range和大小，最后组装时一次完整SHA。
4. 完整段及未完成段的已有字节都可保留；签名失效、429、区间不符或SHA错误暂停，不自动换源、换版本或循环重试。已完成blob继续使用原始SHA回执。
5. 每个blob的新registry入口至少间隔8秒，为观测到的小时额度保留余量。准备器使用固定题序的首次使用顺序，使完整镜像能够较早就绪。
6. 仅连接专用Docker socket `runs/software-panel-v053/docker/docker.sock`，不改共享daemon或代理。标准Docker archive以流式方式交给`docker load`，不额外保存一份大型archive，也不直接操作Docker存储目录。
7. 每镜像以实际config/image ID和linux/amd64身份核对。完整依赖就绪的镜像可在其它blob仍下载时加载和CPU检查。
8. 数据和缓存仅在`/data0`下，保留至少200GiB空闲；加载前再次核对空间。没有删除旧资产或用户数据。

未开始的1ms续传配置已经调整为 **24个CDN连接 + APIBA最多4连接 + 原先最多4个在途连接，总上界32**。这只调整新进程，没有重开或中断原连接。

API流若以后中断，非空partial不会由API入口重新下载。冷却后的1ms Range入口可接收其已关闭的partial：只额外接受精确API域名、同镜像路径、同官方digest及总大小的checkpoint，先验证现有prefix大小和partial SHA，再只请求余下区间。原来源和partial SHA进入range ledger，最终完整SHA仍是官方验收条件。活动下载锁未释放时，接续器只等待，不读写该partial；这不构成对在途连接的中断。

### 签名URL与跨来源持久性

后续必要检查只读取已保存的1ms响应，没有在冷却期追加网络探测。原本地记录实际包含CloudFront `Expires/Key-Pair-Id/Signature` 形式：12:51:14.746723 UTC观测，Expires为13:41:15 UTC，相差约3,000秒，即50分钟。单个大blob或共享队列等待可能超过此期限，不能仅以整批预算或URL未变假定一直有效。公开的 [lease-persistence-review.json](../../artifacts/software-benchmark-v054/images/lease-persistence-review.json) 仅保存字段名、到期时间及原记录摘要，没有复制签名。

接续器现在只对已识别的明确Expires执行有界刷新：距到期120秒以内，或同一CDN返回403且已能确认该lease到期时，针对相同官方blob和原registry地址重新认证、解析URL；每blob最多4次刷新。刷新所读取的仍是尚缺的区间，已完成段不重传。未知到期形式、未到期403、新lease异常或上限耗尽均停止，不将任意403当成过期。

初始lease、刷新lease和小blob共用同一8秒registry许可。按一次许可覆盖一次auth和一次原registry GET估算，约900次请求/小时，给已观察到的1000次/小时额度保留余量；CDN分段不触发额外registry认证。429立即关闭排队入口，保存Retry-After及首个真实故障，后续取消任务不会覆盖限流原因。API与1ms持有同一个目标文件锁，另一来源先完成时只复用同SHA回执；竞争取得锁不会制造重复HTTP传输。

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

后续观察确认r2于23:44:04 CST实际启动，完成proof由9增加到13，并开始Range传输，首个状态没有新429。随后启动 `proworksim-v054-image-retry-supervisor.service`：只对实际429解析其Retry-After，并在不早于该时间且至少间隔60秒后设置同一批次的单次恢复timer。它不改变题单、官方摘要、已下载内容或已有连接；未到期、无合法Retry-After、未知403、摘要/身份错误均不盲目重试。

监督器只读1ms来源已物化的唯一字节作为进展信号，包含partial并去除重叠区间，排除API自身下载和混源prefix中的API字节。这不是流量计费表。初次介入的已运行attempt没有完整起点，因此不会武断认定它“零payload”；后续每次恢复都在启动前保存基线。连续3次冷却恢复仍无新增1ms字节时，将该来源标为外部阻断，不停止其它国内来源。所有自动恢复受最初启动后的96小时窗口限制；未知故障直接终止监督器，正式模型运行仍不获授权。

监督器状态和每次有界决定保存到：

```text
runs/software-benchmark-v054/images/retry-supervisor-r1/state.json
runs/software-benchmark-v054/images/retry-supervisor-r1/attempt-*-start.json
runs/software-benchmark-v054/images/retry-supervisor-r1/outcome-*.json
```

### r2：已记录读取超时的有界续传

00:03:45快照中的实际故障为`The read operation timed out`，不是HTTP429。新版本只对保存为`TimeoutError`或明确读取超时文本、且没有HTTP状态的故障增加独立恢复分支；任何带403的响应、SHA不符、Content-Range不符或其它未知故障仍不自动重试。429继续使用真实Retry-After，不以超时退避替代服务端限流时间。

`proworksim-v054-image-retry-supervisor-r2.service` 在00:14:26 CST启动；只读到主下载服务完全退出后，才依次按60、300、900秒退避安排最多3次恢复。恢复仍是同一个全500题批次、相同官方digest和已保存区间，不重开当前API连接，也不重新请求已完成区间。若连续3个可比较的恢复尝试没有新增1ms来源字节，或耗尽3次读取超时恢复，标记为外部阻断。已有API来源字节不会被用于伪造1ms进展。

新监督器继承r1最初的96小时截止时间，不因版本切换延长窗口；日历timer对启动边界向上取整，避免秒以下精度导致提前执行。r1当时没有待启动timer和已调度恢复，旧状态完整保留。新版本的决定及启动证据位于：

```text
runs/software-benchmark-v054/images/retry-supervisor-r2/state.json
runs/software-benchmark-v054/images/retry-supervisor-r2/launch-receipt.json
runs/software-benchmark-v054/images/retry-supervisor-r2/attempt-*-start.json
runs/software-benchmark-v054/images/retry-supervisor-r2/outcome-*.json
```

新回执观察状态为`monitoring_active_attempt`，已安排的读取超时恢复次数为0。旧下载进程尚在收尾，r2没有以超时为由强制停止它。后续实际网络是否恢复仍需后台状态证明；本次只确认恢复策略的必要离线控制通过，以及新监督器已启动。

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

23:05阶段快照包含10个不同合成CPU控制：metadata正文身份与拒绝篡改2项、全500计划的跨源不一致拒绝及unknown保留2项、镜像依赖一齐即可加载的流水线1项、严格Range及不中断/断点/凭证边界3项、APIBA完整流与缓存/partial保护及禁止跳转2项。

随后仅补做1项混源partial接续控制：2MiB合成blob复用512KiB API prefix，网络严格只取剩余1.5MiB，完成文件与官方预期SHA一致且来源记录保留。至此不同控制共11项，原10项没有因此整批重跑。只对有实际改动的计划控制做了必要复核，没有重跑旧实验、旧17项文件接口控制或真实模型测试。限定Ruff已通过；首次发现的就绪watcher未使用import已修正并仅复查该文件。

lease持久性检查再增加1项窄控制，覆盖明确过期后同源刷新且不重传字节、未知403不重试，以及刷新时429保留Retry-After并停止排队。首次合成执行在429分支发现排队任务仍进入测试替代的许可计数，实际registry门原已检查暂停；补上更早的排队入口检查后通过。随后在保留首故障的新增断言下再次通过，三次执行均保留为同一项控制；此前11项没有重跑。不同控制累计12项，新增真实网络探测和在途流中断均为0。

新增429监督器另有1项必要离线控制通过，覆盖秒数和HTTP日期形式的Retry-After、最小恢复间隔、96小时边界、三次无进展、403/缺失Retry-After拒绝，以及排除API字节的唯一进展计数。不同控制累计13项，此前12项没有重跑。

实际读取超时出现后仅新增1项窄控制，一次执行通过，覆盖60/300/900秒退避、最多3次、96小时边界、三次无进展，以及403/SHA/区间错误和缺失Retry-After拒绝。不同控制累计14项，此前13项没有重跑；新增分支及测试的限定Ruff通过。该控制没有发送网络请求，也没有启动下载容器、评分或模型。

源站限流、连接慢和未完成镜像是准备状态；它们没有被记为模型失败。当前没有完整500环境完成声明，没有新增正式评测授权，也没有训练或GPU占位。

## 2026-10-21 00:18：APIBA 首个大层完整交付

读取已有完成回执确认，首题的 420,167,964-byte 缺层已由 `docker.apiba.cn` 完整交付，增量计算的完整 SHA256 与预锁官方 digest 一致；没有为此再次扫描整层。完成证据见 [apiba-first-complete.json](../../artifacts/software-benchmark-v054/images/apiba-first-complete.json)。原先只取得部分字节的快照保留。API 预取已越过首层完整性门；00:18:20 UTC+8 汇总的完整 blob 字节为 1,990,165,469，已加载镜像仍为 0/500，正式模型调用为0。该结果证明一次真实大层交付，不能据此保证后续全部500镜像的可用性或带宽；FRA节点与无全境内链路保证的记录仍有效。
