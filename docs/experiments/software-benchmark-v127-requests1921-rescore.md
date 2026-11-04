# v127：Requests1921 原候选的限定补评

本轮只对 v125 的 REF `psf__requests-1921`（原物理编号 7239）重新执行一次官方评分。模型已经正常闭合，原补丁、唯一候选锁、生成记录与费用均保留；不重新调用模型、不改补丁、不选择其他工作树。新评分使用独立身份 `score-v127-7239`，旧评分的技术未知原件不会被覆盖。

## 原未知的直接证据

原评分报告确认补丁成功应用，6 项 FAIL_TO_PASS 全部通过；PASS_TO_PASS 中只有 `test_pyopenssl_redirect` 未通过。与此同时，受限 HTTPS 转发记录显示第 49 次连接在连接上游 `16.58.42.220:443` 时超时：`upstream_connected=false`，双向应用载荷均为 0，约 10.01 秒后返回 `upstream_connect_error`。该次连接未建立，因此这份结果不能直接解释为候选代码错误。

其余 73 次连接没有记录网络错误。原 CA 文件仍为原字节，评分侧采用此前明确允许的冻结 CA 配置，证书验证模式为 `CERT_REQUIRED`、主机名验证开启；容器也已正确清理。证据支持“单次上游连接故障导致评分不完整”，不支持已经通过整题；必须由新的完整评分决定结果。

原始证据位于 `runs/software-benchmark-v125/ref-first-generation-r1/grading/score-7239/`，主要包括 `receipt.json`、`quiescence.json` 与 `official-output/transport.json`。

## 保持与变更

- 保持原题、官方基础镜像、官方测试补丁、候选补丁、正常 REF 闭合证据，以及冻结的 DNS/IP 和 CA 配置。沿用 v119 已真实通过的同环境 gold/empty 资格，不重复创建控制容器。
- 只新增一个评分身份和独立日志目录；原请求与候选的 SHA 身份进入新请求、源封存和最终回执。评分路径同时验证原 v125 正常闭合条件与新 v127 资源范围。
- 不对测试代码增加内部重试，也不因再次异常自动重跑。如果仍发生网络或执行故障，新结果继续单列技术未知。
- 正式评分完成后清理本次唯一容器并释放本次预约。只管理新对象，不重启服务，不改变共享服务器挂载、网络、驱动或其他任务。

## 资源范围与准备检查

最多 1 个评分容器，4 CPU、16 GiB；容器 `network=none`、`drop ALL`，仅采用此前 Requests 评分允许的容器内部 `NET_ADMIN`、`NET_BIND_SERVICE`。普通用户转发进程最多建立 1 个受限会话、512 次连接、64 MiB 应用载荷，仅到冻结的 httpbin.org 公网地址 80/443，保持真实 TLS 校验。无模型/API、GPU、数据卷、宿主目录绑定、宿主端口监听或新服务。

监督进程与评分子进程使用固定解释器，各有 4 GiB 自身地址空间上限；加上容器 16 GiB，本次按合计 24 GiB 预约，不能写成宿主两进程合计 4 GiB。它们与评分容器共用原 CPU 池的第 28–31 个索引，和 v126 使用的第 0–27 个索引分开；v127 不等待、停止或重载 v126。曾做一次 512 MiB 监督进程的离线构建探测，但最终采用已有 4 GiB 限额，避免改造子进程继承链；该探测不代表采用了更小的部署限额。

准备只执行离线 CPU 检查：真实资格复用、原候选闭合验证、新身份及子评分模块绑定、候选/生成/配置等替换拒绝、最终只读封存一致性。网络、Docker、API 和执行授权入口在该检查中禁止调用。具体结果见 `artifacts/software-benchmark-v127/scoring-controls-r1/summary.json`；准备通过不等于正式评分已经完成。

运行前仍须对封存的单次评分操作完成具体授权。授权文件不存在时，评分入口拒绝执行。


## 实际收口

本次保留原候选的单次评分已完成，官方结果`resolved=true`；原先连接超时对应的`test_pyopenssl_redirect`也已通过。原候选和测试未改，未调用模型、没有新增API费用。本次唯一容器已清理，quiescent=true、cleanup_errors=[]、create_result_unknown=false，活动资源声明为空。新评分回执在`runs/software-benchmark-v127/requests1921-rescore-r1/grading/score-v127-7239/receipt.json`；旧网络故障回执保留。
