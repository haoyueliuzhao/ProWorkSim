# v183：Pylint-8898 评分启动检查修复

原 gold／empty 两个控制均在官方测试之前失败。真实镜像诊断确认：指定 Python 能正常返回 JSON 并以 0 退出，但启动时还向 stderr 打印 `_distutils_hack` 缺失警告。旧隔离检查把 stdout 与 stderr 合并后直接交给 JSON 解析器，因而误判启动见证不可用。诊断容器已清理，未调用模型或访问网络。

修复仅分离这项隔离见证的 stdout／stderr：严格解析 stdout 的完整 JSON，单独保留原始 stderr 和退出码；非零退出或 stdout 非 JSON 仍拒绝。没有屏蔽 Python site 初始化、删除 `.pth`、修改依赖、官方测试或候选补丁。两个 CPU 检查覆盖真实警告与非法 stdout。

追加同镜像的新 gold／empty 控制，各最多一个容器，4 CPU／16 GiB、network=none、drop ALL、无宿主绑定、端口、GPU或新数据卷。两个评分槽与正在运行的 v181/v182 共用，旧控制原件保留。普通用户控制进程额外限 2 CPU／4 GiB；临时总上界 50 核等价／300 GiB，无共享主机配置更改。此页记录修复与范围，最终准入以实际新控制结果为准。
