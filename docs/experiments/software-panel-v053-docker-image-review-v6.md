# v053 Docker 镜像版本与泄露修复核对

记录日期：2026-10-20，Asia/Shanghai。当前结论是**镜像更新尚未完成，正式派发暂停**，不是“镜像已确认最新”或“已确认修复”。

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

## 已有隔离措施及边界

本项目现有后端在 actor 暴露前，先应用缺陷并隐藏指定测试，再清除 `/testbed` 下旧 `.git` 目录、Python 字节码和测试缓存，重建唯一初态提交，并检查 remote 为空、源码 tree 不变。judge 同样清理历史并独立恢复受保护测试。相关既有控制已通过，本次没有重复运行环境测试。

这些措施覆盖通常的旧 Git 历史读取路径，不构成全文件系统泄露审计：额外 bare repo、外部 `.git` 文件或 alternates、安装目录和依赖缓存中的目标源码副本尚未全面核对。Pydantic editable wheel 的既有单独核查不能推广到所有镜像。官方仓库的 [issue #640](https://github.com/SWE-bench/SWE-bench/issues/640) 另有缓存／额外环境的泄露报告；这是报告者提出的独立路径，不能冒称维护者已经确认或发布修复。

## 后续放行条件

先确定用户所指修复的适用镜像和不可变身份，再取得当前官方 manifest，核对国内源的 manifest/config/layer digest；只补缺失层。如果与本地内容完全相同，可复用内容并记录事实，不能声称新增了修复。国内源缺失或直连失败不回退代理。

实际 image ID 改变时，仅重新准入受影响仓库的原预选任务，并验证相关泄露路径；不按新测试或模型表现更换题目。新资格和运行配置使用独立记录，旧 v5 证据不覆盖。目标身份、可用下载来源及必要环境资格闭合之前，保留全部未启动 slot，正式 GPU 派发不恢复。

## 本机证据

- `runs/software-panel-v053/image-refresh-v6/v5-stop-receipt.json`
- `runs/software-panel-v053/image-refresh-v6/official-latest-comparison.json`
- `runs/software-panel-v053/image-refresh-v6/dockerhub-tag-probe.json`
- `runs/software-panel-v053/image-refresh-v6/domestic-source-probes.json`
- [v5 停止时零回合报告](software-panel-v053-result-v5.md)

本次新增模型加载、模型调用、生成 token、训练和任务测试均为 0。
