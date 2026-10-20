# v053 Docker 镜像版本与泄露修复核对

后续决定：用户已用新方案明确选择 SWE-bench Verified 全500题及三组比较，另授权受管文件能力修复。本文的“评测集待明确”是该决定前的历史状态；当前以后续 [v054 方案](software-benchmark-v054-protocol.md) 为准。原 v053 记录和未启动槽保持，不当作 Verified 的准备或结果。

记录日期：2026-10-20，Asia/Shanghai。后续已找到并实测 `docker.1ms.run` 直连来源，独立官方检查确认 **32 个镜像的当前官方 digest、镜像站 digest 和本地缓存一致，无需重下载**。这解决下载来源和当前版本确认，不代表确认 SWE-smith 已包含 Verified 的泄露修复。正式派发仍暂停，评测集及修复适用范围待明确。下面保留初次失败与后续成功的完整区别。

## 用户澄清与停止记录

用户指出所需核对的是 Docker 镜像，尤其是官方针对数据泄露的修复版本。此前对 Qwen3.5-9B、SWE-smith-py 和 SWE-smith 源码 `main` 的核对不回答容器版本问题；此前“无需重新下载”的结论不能扩展到 Docker 镜像。

本项目 `proworksim-v053-panel-v5.service` 已停止。2026-10-20 20:34:26 的停止回执确认：280 个 slot 全部 pending，attempts 为 0，active 为空；没有模型结果需要重跑或与新镜像混合。监督器保存 `supervisor_received_SIGTERM`，服务以预设暂停退出码结束，MainPID 为 0。此前 v5 环境资格和冻结题单仍保留，但不自动恢复派发。

原 200 题、40 题重复子集、280 个 seed、原始模型与全部数值配置均未改变。`image-refresh-v6` 是本次核对记录目录，不表示已经形成或放行新的正式运行配置。

## 官方修复适用范围

SWE-bench 官方 [issue #465](https://github.com/SWE-bench/SWE-bench/issues/465) 中，维护者于 2025-09-11 宣布重推 SWE-bench Verified 镜像，并在 [PR #471](https://github.com/SWE-bench/SWE-bench/pull/471)／swebench 4.1.0 修订构建流程，移除未来 Git 历史，同时保留基准提交之前的历史和标签。该公告可以证实 Verified 的修复，不能单独证明 SWE-smith 镜像也经过同次重建。

SWE-smith 当前锁定官方源码的 [Python 构建入口](https://github.com/SWE-bench/SWE-smith/blob/9b74ac08118a85c39c356802f7961893af73e07f/swesmith/profiles/python.py#L47-L66) 仍克隆镜像仓库，[容器初始化入口](https://github.com/SWE-bench/SWE-smith/blob/9b74ac08118a85c39c356802f7961893af73e07f/swesmith/profiles/base.py#L493-L530) 检出任务分支。镜像名称末尾的八位 SHA 表示题库仓库源码版本，不是容器构建日期或泄露修复版本。宿主安装了 swebench 4.1.0 也不会自动改写已经下载的镜像内容。

本次未找到明确对应 SWE-smith 的修复版 tag 或官方修复 digest 清单。这是证据尚未取得，不是断言官方从未修复。已向用户请求其看到的修复公告或镜像名称/tag，以确定目标。

## 本地镜像与当前远端核对

专用 Docker daemon 实际有 32 个镜像，32/32 config image ID 与既有官方 manifest 和三份导入回执一致。来源索引为：

- `runs/software-panel-v053/parallel-images/eight-image-assets.json`
- `runs/software-panel-v053/prefetch-ranks09-24-v1/sixteen-image-assets.json`
- `runs/software-panel-v053/prefetch-ranks25-32-v1/eight-image-assets.json`

本地 config 构建时间为 2025-07-12 至 2025-07-16。构建时间早不必然等于远端 tag 已过时；此前在 2026-10-20 取得的 manifest 也不能证明包含特定漏洞修复。标准 `docker load` 后 RepoDigests 为空，官方 manifest/config 身份保存在上述外部索引，不能只看本地 tag 判断。

20:36–20:37 对 32 个官方 `latest` 发起一次有界元数据核对，显式 `ProxyHandler({})`、禁止重定向、每响应最多 128 KiB、4 路并行，不请求镜像层。全部在官方认证入口直连失败，响应正文为 0；结果是 **32 个当前版本未知**，不是“32 个均未更新”。随后另一官方 Docker Hub 标签 API 的单个代表请求同样直连不可达。网页工具也未取得该 Docker Hub 标签数据。

本次没有得到可验证的当前官方替换 digest，没有重新下载、覆盖 tag、删除镜像或修改 Docker daemon 配置。

## 国内直连来源

仅对一个代表镜像 Faker 的原固定 digest 做两个有官方服务文档的候选探测，没有扩大为全库下载：

| 候选 | 实际结果 | 能否提供本次可验证镜像 |
| --- | --- | --- |
| DaoCloud `m.daocloud.io` | DNS/TLS 正常；同域匿名认证后 manifest 返回 403，原因是镜像不在白名单 | 未取得 manifest |
| 腾讯 `mirror.ccs.tencentyun.com` | 本机 DNS 无法解析；官方文档描述为腾讯内网服务 | 未取得 manifest |

实际读取响应正文合计 1,455 字节，不含 HTTP/TLS 开销；代理使用、重定向跟随、镜像层请求均为 0。这不证明所有国内源都不可用，也不证明上述服务可以取得新版。

## 后续来源处理与成功证据

用户要求继续处理来源失败后，检查了服务器已有镜像配置及服务方文档，并进一步做有界直连探测。没有改动共享 Docker 配置，也没有为通过探测而启用代理。

| 来源 | 后续实测结论 |
| --- | --- |
| 南京大学 | DNS 正常，HTTPS 403 |
| SJTUG | DNS 正常，TLS 握手失败 |
| DaoCloud 替换域 | 仍指向同一认证与白名单服务，不能通过替换域名解决许可范围问题 |
| 轩辕 | 免费节点 HTTP 403，`TOOMANYREQUESTS`；未购买服务或注册账户 |
| Docker Proxy | HTTP 401，未提供可使用的标准匿名认证挑战 |
| 1Panel 候选入口 | 直连 TLS 连接被重置 |
| 毫秒镜像 `docker.1ms.run` | 32 个 manifest 全部取得并核对；小型 config、完整极小层及大层有界 Range 均取得成功回执 |

### 官方版本身份

本项目 [GitHub Actions 运行 39427123231](https://github.com/haoyueliuzhao/ProWorkSim/actions/runs/39427123231) 使用固定提交 `e4d6b6335abc735b9f4898f134c8a18e4b92bbb6`，在 21:03:15–21:03:18 CST 直连官方认证与 registry，仅查询 32 个指定 `latest` manifest。每份正文 SHA 与官方响应摘要核对，通过数 32，changed 0，unknown 0；没有获取 config/layer blob。工作流、任务日志及 artifact 保存了查询时间和完整逐项结论，宿主失败请求不改写成成功。

本机毫秒镜像另一次检查同样取得 32/32 manifest，正文 SHA、响应头及 config descriptor 均与原官方记录相同。将两份证据逐镜像合并，得到当前官方／国内镜像服务／本地缓存三方一致，见 [机器摘要](software-panel-v053-domestic-registry-v6.json)。因此本轮没有缺少的新版本层，没有进行整镜像重拉或重新执行不变环境资格。

### 文件交付验证与实现

1ms registry 返回的文件交付域为 `cloudfront-docker-cf.mrs.1ms.run`。初次默认客户端请求得到 403，其短正文摘要对应 `error code: 1010\n`。随后使用真实项目 User-Agent 和正常 `Accept: application/octet-stream` 取得：

- 5,551 字节 config，HTTP 200，完整 SHA 与 manifest 一致；
- 164 字节层，HTTP 200，完整 SHA 与 manifest 一致；
- 431,740,248 字节层的前 4,096 字节，HTTP 206，Content-Range 精确匹配，内容与已有完整验证缓存的对应前缀一致。没有重下载或重新 hash 整个大层。

请求头及时间都发生变化，不能把成功唯一归因于 User-Agent，也不能把一次探测说成长期可用性认证。交付响应的 CF-Ray 标记为 `SIN`；本结论是“国内镜像服务可直连且未使用宿主代理”，不宣称所有 CDN 节点及整个链路均位于中国大陆。

新增 [固定摘要 blob 下载入口](../../tools/DOMESTIC_REGISTRY_DOWNLOAD.md)，只允许精确的 registry 与交付域，显式禁代理，逐跳检查，跨域删除 bearer，完整 SHA/大小核验，断点绑定稳定原 URL。完整缓存直接复用，不为认证或重哈希而额外联网。元数据和身份选择与文件传输分离，工具不自动升级镜像。

3 项新增和 5 项受改动影响的离线控制通过，限定 Ruff 通过；随后根代理使用实际 CLI 完成一次 **164 字节**下载，覆盖匿名认证、重定向、去认证头和完整 SHA 的集成路径。回执文件为 `runs/software-panel-v053/image-refresh-v6/cli-smoke-164.blob.download.jsonl`，结果 `download_complete`。没有进行镜像导入、GPU 或模型操作。

## 已有隔离措施及边界

本项目现有后端在 actor 暴露前，先应用缺陷并隐藏指定测试，再清除 `/testbed` 下旧 `.git` 目录、Python 字节码和测试缓存，重建唯一初态提交，并检查 remote 为空、源码 tree 不变。judge 同样清理历史并独立恢复受保护测试。相关既有控制已通过，本次没有重复运行环境测试。

这些措施覆盖通常的旧 Git 历史读取路径，不构成全文件系统泄露审计：额外 bare repo、外部 `.git` 文件或 alternates、安装目录和依赖缓存中的目标源码副本尚未全面核对。Pydantic editable wheel 的既有单独核查不能推广到所有镜像。官方仓库的 [issue #640](https://github.com/SWE-bench/SWE-bench/issues/640) 另有缓存／额外环境的泄露报告；这是报告者提出的独立路径，不能冒称维护者已经确认或发布修复。

## 后续放行条件

当前版本身份及国内直连来源已经闭合，但用户所指泄露修复适用的评测集仍需区分。用户补充“主要就是评测集”，随后已明确询问继续原 SWE-smith 200 题还是改用 SWE-bench Verified；未得到选择前不擅自替换题库。两套数据不能混成同一面板，官方 Verified 的修复公告不能替代 SWE-smith 的适用性证据。

如果后续明确需要改变 image ID，仅重新准入受影响仓库的原预选任务，并验证相关泄露路径；不按新测试或模型表现更换题目。新资格和运行配置使用独立记录，旧 v5 证据不覆盖。当前保留全部未启动 slot，正式 GPU 派发不恢复。

## 本机证据

- `runs/software-panel-v053/image-refresh-v6/v5-stop-receipt.json`
- `runs/software-panel-v053/image-refresh-v6/official-latest-comparison.json`
- `runs/software-panel-v053/image-refresh-v6/dockerhub-tag-probe.json`
- `runs/software-panel-v053/image-refresh-v6/domestic-source-probes.json`
- `runs/software-panel-v053/image-refresh-v6/official-latest-via-ci.json`
- `runs/software-panel-v053/image-refresh-v6/ms-latest-32-comparison.json`
- `runs/software-panel-v053/image-refresh-v6/ms-config-error-diagnostic.json`
- `runs/software-panel-v053/image-refresh-v6/ms-small-layer-and-range-control.json`
- [v5 停止时零回合报告](software-panel-v053-result-v5.md)

本次新增模型加载、模型调用、生成 token、训练和任务测试均为 0。
