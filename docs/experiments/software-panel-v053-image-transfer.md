# v053 原始镜像下载适配记录

日期：2026-10-20。本轮只修复固定候选仓库的官方镜像传输，没有修改已冻结的任务、评分器、模型设置或科学源码。

## 问题与观察

首次八仓库预取时，其余完整层已下载数 GiB，但共同层 `a71ffc639925…` 的单连接持续低速，所有镜像都在等待它闭合。官方 manifest 规定该层为 **466,932,925 bytes**。现场曾观察约 114 MiB／18 分钟，不能据此推断整条链路的带宽或唯一故障原因。

从官方 registry 获取的签名 CloudFront 地址支持正确的 HTTP 206 和 Content-Range。两个独立 4 MiB 样本分别用时约 19.1 秒、27.2 秒；另有 TLS EOF。一次受限直连对照被连接重置，后续继续使用服务器既有代理。没有调整共享代理或其他业务服务。

专用 Docker 是 **29.3.1，Git commit `f78c987`**。核对了对应官方源码的临时文件／Range 恢复逻辑，而非只沿用旧版本推断：普通网络读失败保留已下载偏移，重试尝试从文件末端续传；不接受 Range 或校验失败等情况仍可能触发重下。[对应 Moby 源码](https://github.com/moby/moby/blob/f78c987ad371/daemon/internal/distribution/pull_v2.go)

主代理只重连了专用 daemon 的一条明确四元组连接。实际所有原临时文件都保留，观察不到文件大小下降；回执为 `runs/software-panel-v053/docker/exact-socket-reconnect.json`。重连后仍只约 219 KB/s，因此另外准备官方内容的并行获取。这个操作没有重启 daemon。

## 原始内容如何保持不变

对预锁顺序的前八仓库，获取官方原始 manifest 和 config，验证 registry 返回的 manifest digest、config SHA-256 与字节数；清单保存在：

```text
runs/software-panel-v053/parallel-images/eight-image-assets.json
```

完整的 Docker 暂存层由主代理只读复制。复制器只接受上述 manifest 中的字节数和完整压缩层 SHA；第一批验证八层，扩展到八镜像后再验证二十九层。没有直接写 Docker 内部缓存。

临时文件已经被 Docker 注册并移除的两个基础层，以及两个仍受慢连接影响的层，从官方 registry 重定向地址补齐。并行下载使用 **16 worker、4 MiB 分块**，逐块要求正确 Range；拼接后对新完整压缩层做一次 SHA-256 检查。

| 补齐内容 | 完整内容字节数 | 本次观察耗时 | 验证结果 |
| --- | ---: | ---: | --- |
| 公共层 `a71ffc…` | 466,932,925 | 489.09 秒 | manifest SHA 相同 |
| 两个基础层 `9cb31e…`、`400078…` 及原 config | 29,535,941 + 215,223,965 | 197.40 秒 | 两层与 config 均匹配 |
| gspread 层 `7f0ef2…` | 377,257,788 | 252.25 秒 | manifest SHA 相同 |

这些阶段部分重叠，不能直接相加成为总墙钟时间。数字是有效内容及阶段耗时，不是总网络流量；前序 partial download、探测和失败重试另留原记录。最后一个 gspread 分块曾另开备用连接，但该备用尝试超时，未用于最终内容；原并行下载最终独立完成并通过完整 SHA。

早期多数分块很快完成，尾部重试明显拖长总耗时。因此本记录没有把前几十秒的峰值吞吐当作全程速度，也不把一次现场修复解释为稳定的网络加速倍数。

## 标准 Docker load 归档

最终获得 **8 个原始 image config、41 个独立原始压缩层**。以标准 Docker-load manifest 打包，保留各原始 config 的字节及对应官方 tag，不重新 build 镜像。

```text
路径：runs/software-panel-v053/parallel-images/eight-original-images.docker.tar
大小：4,430,786,560 bytes
写入时 SHA-256：
7e11b4a88f1b286911448178d43282c70c5c275c1234697e2e6a9c50e6597251
```

构建耗时 8.68 秒。复用各层已经完成的 SHA 证明，只核对归档读取前后的文件大小、设备、inode、mtime 和 ctime；没有重复手工哈希已有数 GiB 层。外层 tar 的 SHA 在写入时同时计算。标准 Docker load 仍会核对 config 中的解压层 diffID。

`parallel-images/eight-image-archive-receipt.json` 保存八个预期 image ID、每项输入的来源回执和 stat 身份。完整配置 ID 必须在导入后逐个匹配。例如首个 Faker 镜像的原始 ID 为：

```text
sha256:dd3b318d6989d5bb963d54e96b363baddbf1ea8762e0c093c4027f52df012849
```

标准 Docker load 已完成，退出码为 0，耗时 **172.41 秒**。八个实际 image ID 全部逐一匹配官方 config 的预期 SHA，`parallel-images/docker-load-receipt.json` 的 `passed=true`；实际导入日志为 `parallel-images/docker-load.log`。该步骤模型调用和创建任务容器数均为 0。镜像内容身份已核对，clean／bug／gold 任务资格仍须分别完成。

## 运行衔接和证据范围

主代理在导入前受控停止了仅处于等待镜像状态的 pipeline-v1，以及八个属于本轮的 CLI pull。专用 daemon 保持运行，完整临时层事先复制保存；`pre-model-transfer-transition.json` 记录当时模型调用为零、容器为零。旧 v1 的行政停止和零模型报告保留。导入完成后，pipeline-v2 已按相同源码 `34a445d`、相同 backend 配置、候选顺序和 seed 启动 CPU 准入；状态记录为 `runs/software-panel-v053/pipeline-v2/pipeline-state.json`。本次传输修复没有产生模型回合。

下载脚本回执中的“不取消旧下载”指该下载器自身没有实施取消；整体流程中由主代理执行的后续行政停止以上述 transition 为准。两者不是同一操作主体。

本轮新增下载工具仅位于 `runs/software-panel-v053/parallel-images/`，没有修改被冻结的 `src/` 或 `scripts/`。全部准备工作不产生模型 token、训练更新或正式任务成绩。镜像导入后仍须执行 [环境准入规则](software-panel-v053-environment.md)，形成二十仓库／二百题的实际资格，再进入后续模型阶段。
