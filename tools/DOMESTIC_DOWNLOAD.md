# 后续单文件资产下载入口

本入口只用于后续资产获取，不改变正式评测的配置、既有完整数据、`src/`、`scripts/` 或冻结快照。入口验证没有进行真实资产下载、测速、镜像连通性验证或 GPU 操作；另外进行了下文列明的少量版本元数据查询及专用 Docker 服务配置切换。

端点是**配置候选**：`modelscope.cn`、`www.modelscope.cn`、`cdn-lfs-cn-1.modelscope.cn`、`hf-mirror.com`。这里不宣称它们已经实测可用，也不凭域名宣称实际网络路径或服务器物理位置已被证明在国内。没有允许任意 `.cn`，没有添加未经确认的 Docker 镜像。

## 用法

先从已锁定的资产清单取得准确 SHA256 和字节数，再调用：

```bash
.venv/bin/python -B tools/domestic_asset_download.py \
  --url 'https://modelscope.cn/models/<模型>/<名称>/resolve/<固定版本>/<文件>' \
  --output 'runs/assets/<文件>' \
  --expected-sha256 '<64位SHA256>' \
  --expected-bytes '<准确字节数>'
```

URL 示例只是参数结构，不是已验证的下载地址。默认策略文件为 `config/domestic-download-policy.json`；`--policy` 可以指定保留相同硬限制的策略子集，不能借此加入未知域名、代理、HTTP 或原站回退。

每个请求使用标准库 `ProxyHandler({})`，不查询或继承 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY 及其小写形式。自动重定向被禁用；程序逐跳检查 HTTPS、精确域名和端口后，才发起下一次请求。跳向原站、未列域名或 HTTP 会在下一请求之前停止。TLS 使用标准库正常证书验证。

## 减少重复传输

- 下载完成或首次核验现有文件时保存 `<文件>.verified.json`，绑定预期 SHA/字节数和 dev、inode、size、mtime_ns、ctime_ns。完整文件身份不变时直接复用，不再次读取大文件算 hash，也不联网。没有完成凭据或 stat 改变时才执行必要的本地完整 hash，成功后更新凭据；不符时拒绝覆盖。相同内容改用另一个允许的国内候选 URL 不会使已有完整文件重新 hash。
- 未完成文件放在 `<文件>.part`，本地断点回执放在 `<文件>.part.json`。续传前检查同一 URL、预期 SHA/字节数、当前断点长度及本地前缀 hash。
- 续传只请求 `Range: bytes=<已有长度>-`，必须收到匹配的 206、精确 Content-Range 和一致的 Content-Length（如果服务器提供）。服务器返回完整 200 或不匹配的区间时，不追加，不自动从头下载。
- 网络中断后保留已经落盘且有一致回执的断点；使用同一命令显式继续。回执与文件不一致时暂停，不猜测或静默截断。
- 收齐后必须同时满足全长和完整 SHA，才发布目标文件。完整 hash 失败的文件保留为 partial，不自动换源或重下。

断点 hash 证明的是本地文件与断点回执一致；它不替代最终完整文件与固定预期 SHA 的比对。文件锁阻止本入口对同一目标同时写入。

## 记录与本轮离线验证

默认来源日志为 `<文件>.download.jsonl`，保留初始 URL、逐跳来源、预期及实际完整 SHA、字节数、缓存命中、断点状态、拒绝原因和策略 SHA。`payload_bytes_received` 统计本次读取返回的响应正文，不含 HTTP/TLS 开销，不能当作实测链路总流量。

五个离线控制通过，使用标准库真实 opener/重定向处理链与替代 HTTPS handler，没有外部网络请求：

1. 环境代理变量即使存在也不会被查询或使用；完成文件再次调用不会联网。现有文件首次核验后，禁用 hash 函数并更换允许的镜像 URL，仍能直接复用；相同内容换成另一 inode 时才重新核验。
2. 外域重定向没有第二次请求。
3. HTTPS 降级为 HTTP 没有第二次请求。
4. 服务器忽略 Range 返回 200 时不追加、不回退；后续显式有效续传仅读取剩余字节。
5. Content-Range 不匹配时同样保留原断点；后续有效续传完成最终 SHA 验证。

限定 Ruff 通过。这些是离线协议与文件处理控制，不是候选镜像的实际可用性证明。

## 当前服务器落实情况（2026-10-20）

- 原有 14 个运行目录中的联网下载入口已经归档原文及 SHA，并替换为不联网、退出码 78 的停用入口。旧 `proworksim-v053-image-prefetch.service` 已持久 mask，状态为 inactive/dead。历史原件仅用于审计，不得重新作为下载入口。
- 仅对本项目 `proworksim-v053-docker.service` 清除了 daemon 配置中的代理，并安装 [docker-direct-download.conf](../config/docker-direct-download.conf) 到该服务的 `/etc/systemd/system/proworksim-v053-docker.service.d/90-direct-download.conf`。专用 daemon 实际报告 HTTP/HTTPS 代理为空、NoProxy 为 `*`。共享 Docker 和其他项目代理没有修改。
- 切换前确认正式任务尝试数为 0、无活动 worker、专用 daemon 无运行容器，暂时冻结本项目监督进程约 2.36 秒，完成切换后恢复。原 32 个缓存镜像的 ID 不变。没有为验证代理而重新拉取镜像。
- 尚未配置经确认可用的国内 Docker registry。后续镜像只复用已有缓存，或通过符合下载策略的归档离线导入；不能把清空代理理解为允许直接回退 Docker Hub。

本机操作回执：

- `runs/software-panel-v053/legacy-network-retirement-receipt.json`
- `runs/software-panel-v053/legacy-network-unit-mask-receipt.json`
- `runs/software-panel-v053/direct-download-transition-1792498125393315796.json`

上述回执随运行数据保存在本机，不作为实验成绩，也不构成镜像端点的可用性验证。

## 版本选择与镜像同步

新批次准备资产前，先读取官方发布记录或分支提交的小元数据，记录查询时间、明确的 release/tag 或 commit，以及镜像对应版本。区分“最新稳定发布”“当前 main”和“本实验锁定版本”，不能仅凭文件名、下载日期或 `latest`/`main` 别名宣称版本最新。镜像来源还应与选定官方版本的文件大小及 SHA 对齐，避免镜像延迟或同名错版本。

现有 v053 已完成题单与配置冻结，继续复用锁定版本；查到上游更新时单列记录，不在同一批 280 回合中直接替换。以后新批次在准备阶段选择经确认的新版本，再冻结具体 revision。官方元数据不可达、镜像未同步或哈希无法对应时，明确记录“未确认”并暂停对应新资产下载，不启用代理或拉取大文件来试错。

2026-10-20 20:19（Asia/Shanghai）在本服务器进行了一次有界、直连且禁用重定向的官方元数据核对，每响应上限 256 KiB：

| 资产 | v053 锁定 revision | 当次核对结论 |
| --- | --- | --- |
| Qwen/Qwen3.5-9B | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` | 官方 Hugging Face API 直连返回 `Network is unreachable`，是否为当前最新版未确认 |
| SWE-bench/SWE-smith-py | `77cab9055d42ab4a5c25c89a8f937096db13558e` | 同上，是否为当前最新版未确认 |
| SWE-bench/SWE-smith 源码 | `9b74ac08118a85c39c356802f7961893af73e07f` | 官方 GitHub API 当前 `main` 与锁定版本一致；这不是“最新稳定 release”的判定 |

官方查询地址：[模型 main](https://huggingface.co/api/models/Qwen/Qwen3.5-9B/revision/main?blobs=true)、[任务池 main](https://huggingface.co/api/datasets/SWE-bench/SWE-smith-py/revision/main)、[源码 main](https://api.github.com/repos/SWE-bench/SWE-smith/git/ref/heads/main)。本机原始回执在 `runs/software-panel-v053/version-audit-direct/`；唯一成功的响应正文为 336 字节。失败请求未改用代理，未由此触发权重、数据或镜像重新下载。

同日随后使用独立网页检索工具完成官方页面补充核对，没有重试宿主失败接口或启用宿主代理。两个仓库的 `main` 文件页首项提交链接均与锁定的完整 SHA 一致：

- [Qwen3.5-9B main 文件页](https://huggingface.co/Qwen/Qwen3.5-9B/tree/main) 指向 [c202236235762e1c871ad0ccb60c8ee5ba337b9a](https://huggingface.co/Qwen/Qwen3.5-9B/commit/c202236235762e1c871ad0ccb60c8ee5ba337b9a)。
- [SWE-smith-py main 文件页](https://huggingface.co/datasets/SWE-bench/SWE-smith-py/tree/main) 指向 [77cab9055d42ab4a5c25c89a8f937096db13558e](https://huggingface.co/datasets/SWE-bench/SWE-smith-py/commit/77cab9055d42ab4a5c25c89a8f937096db13558e)。

因此，这三项主资产的锁定提交均与本次官方查询所示 `main` 一致，无需因本次版本核对重新下载。上述网页证据不覆盖镜像站实际同步状态，也不证明所有依赖都是各自最新 release；正式任务环境镜像继续使用与任务及代码提交对应的固定版本。原 API 失败回执保留，不改写成请求成功。

用户随后澄清需要核对 **Docker 镜像的官方泄露修复版本**。上段三个仓库的 `main` 结论不能用于断言 Docker 镜像最新或无需更新。当前 v5 已暂停；官方镜像当前 digest 直连未取得，两个国内候选也未提供可验证 manifest，更新尚未完成。详见 [Docker 镜像核对记录](../docs/experiments/software-panel-v053-docker-image-review-v6.md)。此前的环境准备完成不自动覆盖新增镜像要求。

## 官方 Docker 元数据的独立核对

宿主无法直连官方 registry 时，使用本项目 [GitHub Actions 工作流](../.github/workflows/docker-image-manifests.yml) 在独立 runner 上直连官方认证与 manifest API。输入为 [32 镜像固定库存](../config/v053-docker-image-inventory.json)，执行器为 [audit_official_docker_manifests.py](audit_official_docker_manifests.py)。该流程只取小型元数据，不取 config/blob 内容或镜像层，也不加载模型、修改部署或使用主机代理。

工作流只在这三个指定文件变动或手动触发时运行，读取权限、10 分钟上限、4 路并发，保存逐项结果和原始 manifest 为 artifact，并在日志输出带查询时间的精简结果。必须等真实运行回执才能判断当前官方 tag；本地离线控制通过不代替远端查询。镜像站提供的 `latest` 另与这些官方 digest 对照，不能自证上游最新。
