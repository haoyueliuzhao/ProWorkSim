# v0.5.3 固定候选官方镜像传输记录

本文记录环境资产准备，不是任务资格结果或模型成绩。镜像来源仍是冻结候选表中的官方镜像；下载先后不改变候选仓库排名、环境准入规则或最终题单抽样规则。

最初八个镜像的慢连接诊断、已完成层复用、4,430,786,560 bytes 标准归档及八个 image ID 验证，完整保留在[前八镜像历史记录](software-panel-v053-image-transfer-initial-eight.md)。

## 截止时点与已完成范围

以下数量对应 **2026-10-20 06:40:41 UTC / 14:40:41 CST** 的只读快照；后台仍继续传输，后续状态以运行回执为准。

- 原先排名 1–8 的 8 个官方镜像已加载。
- 本轮排名 9–24 的 16 个镜像中，已有 **2 个完成标准 Docker load 且实际 image ID 与官方 config digest 完全一致**：`andialbrecht/sqlparse`、`keleshev/schema`。
- 同一时点已有 5 个镜像的全部压缩层校验完成，其中另 3 个尚未产生成功加载回执。不能把“层已就绪”写成“镜像已加载”。
- 第 25–32 个候选的 8 份官方 manifest/config 元数据已冻结；该批大层尚未开始下载。
- 因而此快照证明共 **10 个镜像已加载**，不证明全部 32 个已完成，更不证明任何新增任务通过 clean/bug/gold 资格或模型推理。

快照：`runs/software-panel-v053/prefetch-ranks09-24-v1/speedup-rate-and-load-snapshot-v1.json`。

| 新增已加载仓库 | 官方 config digest / 实际 image ID | 加载回执 |
| --- | --- | --- |
| andialbrecht/sqlparse | `sha256:42aae13ca2fe711b32c16d19af8bb8a5d0d553d8d6ae6905a1905ea6577fe4cd` | `prefetch-ranks09-24-v1/loads/auto-001/docker-load-receipt.json` |
| keleshev/schema | `sha256:9f508bf751081f8fabbecb40c4ab03a43d4846f85496bc4598fa7a95b0cae3f2` | `prefetch-ranks09-24-v1/loads/auto-002/docker-load-receipt.json` |

表中相对路径均位于 `runs/software-panel-v053/`。两个加载回执 SHA-256 分别为 `0e5b426ee2e0ca53e8549c5a78bed3950710b8d378afa9b72f6d772eb54c138d`、`2680cc505b590fe162736fb30189eb3971f7a0b20ef15880196c29c6e435b417`。

## 固定来源与身份链

候选表仍为 `artifacts/software-panel-v053/candidate-inventory.json`，SHA-256：

```text
09f30d93a0faaee285e750407e2dafed5cfdc5b12cfb3c6d93f8592d90995ada
```

| 范围 | 固定资产索引 | 索引 SHA-256 |
| --- | --- | --- |
| 合格候选排名 9–24 | `prefetch-ranks09-24-v1/sixteen-image-assets.json` | `c23d5e76ea4532169850168e69a2a59654c4c092180db0f5980c396a98990f0f` |
| 合格候选排名 25–32 | `prefetch-ranks25-32-v1/eight-image-assets.json` | `07731cca2bf19d6bd139ae136c2bf435cfe06f1b334434aa607faf7d1880a2e4` |

排名 9–24 依次为 sqlparse、channels、parse、schema、fvcore、python-readability、parsimonious、graphene、result、thefuzz、daphne、records、dvc、pyasn1、grafanalib、safety。排名 25–32 依次为 tldextract、tomli、tinydb、paramiko、dominate、xmltodict、mido、voluptuous。完整组织名、profile slug、官方镜像名、manifest 与 config digest 都保存在上述索引中。

元数据来自官方 Docker registry；manifest 内容摘要须等于 registry 返回的 `Docker-Content-Digest`。如存在多平台索引，仅选唯一的 `linux/amd64` 项并核对其声明摘要。config 原始字节须同时符合 manifest 的大小和摘要。压缩层通过官方 registry 提供的 HTTPS CDN 地址获取；每个 Range 分段必须符合声明的字节范围和长度，完整层拼接时一次计算 SHA-256 并核对官方 manifest。然后使用标准 Docker archive、`docker load` 与 `docker image inspect` 核对原始 config ID，没有直接编辑 Docker 存储。

排名 9–24 共 73 个不同压缩层，其中 **7 个公共层、940,997,275 字节**直接复用原有核验回执。复用前核对路径、设备、inode、大小及时间戳身份，不重新 hash。新增传输需求为 **66 层、12,963,207,488 字节**。截至快照共有 62/73 层具备完整摘要回执；分段完成不等于完整层校验完成。`fvcore` 单个大层为 6,585,568,889 字节，是该批主要的剩余传输量。

第 25–32 批元数据有 40 个不同层，相对当前已核验公共层约需新增 **3,296,718,576 字节**。此数是准备时估算，启动后仍按既有层身份回执复用；不能将它当作实际网络消耗。

## 受控提速与实际窗口

初始使用一个全局 16-worker 池，每段最多 2MiB。第一次调整为逐层完成即核验、发布就绪列表并自动加载，避免等待整批所有大层。此后经明确授权，将唯一全局池提高到 **48 workers**；没有同时启动第二批额外 Range 池。

这次提速仅停止了已核对 PID 与启动时间的本代理下载 supervisor、加载 watcher，以及下载 supervisor 的 16 个直接 `curl` 子进程。没有停止其他下载进程。停止后保留 **1425 个完整分段、2,883,625,354 字节**；14 个未完成小分段需要重试。按当时 16 个在途连接计算，可能被中断的在途数据上界为 **32MiB**。原先已完成的分段通过 Range/长度证据复用，57 个已核验层直接复用，不重新下载或重复 hash。

相关不可覆盖回执：

- `prefetch-ranks09-24-v1/speedup-before-1792478000229444034.json`
- `prefetch-ranks09-24-v1/speedup-pause-1792478039955302230.json`
- `prefetch-ranks09-24-v1/speedup-rate-and-load-snapshot-v1.json`

| 窗口 | 持续时间 | 本窗口新完成网络字节 | 平均速度 |
| --- | ---: | ---: | ---: |
| 16 workers，停止前最近一个约 5 分钟窗口 | 277.27 秒 | 367,001,600 | 1.324 MB/s |
| 48 workers，重启后稳定约 5 分钟窗口 | 292.39 秒 | 1,457,761,750 | 4.986 MB/s |

这里 MB/s 使用十进制单位；48-worker 窗口剔除了旧完整分段的复用字节。观察窗口速度约为原窗口的 3.77 倍。后台负载及网络状态并未做实验控制，因此这是实际传输观测，不是严格的并发性能基准，也不是余下传输时间的保证。

重启后的排序键预先固定为 `(是否大于 1GiB, 仓库排名是否大于 16, 层大小, 仓库排名, 分段编号)`，使前批较小镜像先完整，再处理其余小层及 `fvcore` 大层。该键只调度资产传输，不使用模型成绩，也不删除或重排科学候选表。

## 独立后台接续

用户级 systemd 单元：`proworksim-v053-image-prefetch.service`。

服务状态核对时点为 **2026-10-20 06:41:13 UTC / 14:41:13 CST**：`active/running`，MainPID `401231`。记录见 `prefetch-ranks09-24-v1/systemd-supervisor-start-receipt.json`。当时正在运行的首批下载 PID 为 `283951`，加载 watcher PID 为 `287258`；这些 PID 只描述该时点，后续以动态状态为准。

协调器 `runs/software-panel-v053/image-prefetch-supervisor.py` 由 systemd 独立运行，监控现有首批进程。若交互执行会话退出而下载进程中断，协调器先等待该批剩余 `curl` 子进程结束，再以保留的完整分段和层回执续传，避免重叠产生第二个全局下载池。就绪镜像由独立 watcher 分批构造标准 archive、加载并核对原始 config ID。

只有在排名 9–24 的 16 个镜像全部产生成功加载回执、且旧批已没有 Range 下载进程后，服务才自动启动排名 25–32 的下载与加载。后批入口自身也要求前批成功回执，继续复用前批已核验层。无需 agent 后续人工调用，不依赖 agent turn 持续运行。公开传输或加载失败会保留失败回执并暂停；退出码 78 不由 systemd 自动循环重试。

持续状态与完成证据：

```text
runs/software-panel-v053/image-prefetch-supervisor-state.json
runs/software-panel-v053/image-prefetch-supervisor-events.jsonl
runs/software-panel-v053/prefetch-ranks09-24-v1/layer-index.partial.json
runs/software-panel-v053/prefetch-ranks09-24-v1/loads/*/docker-load-receipt.json
runs/software-panel-v053/prefetch-ranks09-24-v1/docker-load-receipt.json
runs/software-panel-v053/prefetch-ranks25-32-v1/docker-load-receipt.json
runs/software-panel-v053/image-prefetch-supervisor-completion.json
```

最后三个完成文件应由后台在相应工作实际完成后产生；**本文不声称这些文件在快照时点已存在**。运行辅助代码、分段、原始大层及详细回执均位于已忽略的 `runs/` 下。本次资产准备没有调用模型，没有执行任务资格测试，也没有修改候选表或正式实验源代码。
