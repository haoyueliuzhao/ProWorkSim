# v053 当前服务器运行时前置修订

日期：2026-10-20。此记录只覆盖 launcher 修复及只读资源盘点，不是正式任务成绩，也没有新模型生成。

## 修复范围

上一轮临时验证发现两个独立问题：受限 `/dev` 视图内 CUDA 枚举不一定保留宿主物理编号；CUDA 初始化还需写自身 `/proc/self/task/*/comm`。上一轮仅在临时副本修订后验证过原始 9B FP32 短生成，本轮将同一修复正式加入私有运行入口。

`run.sh --gpu 7,3` 现在在进入命名空间之前，逐个查询物理编号对应的完整 UUID。返回编号必须匹配请求，UUID 必须是完整有效格式，重复编号、重复 UUID、查询或解析失败、缺少查询工具均在进入命名空间之前拒绝。原有设备节点存在性检查继续在挂载前执行。CUDA 与 NVIDIA 可见设备变量按请求顺序使用 UUID；`PROWORKSIM_HOST_GPU_DEVICES` 保留原物理编号作为宿主证据。CPU 入口不查询 NVIDIA。

GPU 可信运行时的 `/proc` 改为可写，保留 `nosuid,nodev,noexec`。CPU 入口仍只读；业务执行沙箱的 `/proc` 隐藏规则没有改变。这里是模型驻留运行时适配，没有更改模型参数、采样、项目业务执行器或评分协议。

两个 helper 已部署到 `/data0/zhuxinrui/proworksim-runtime`，每个原件只备份一次。部署前 SHA、部署后 SHA、备份路径及必要验证收据见 [deployment.json](../../artifacts/software-panel-v053/runtime-adaptation/deployment.json)。

## 必要验证及失败记录

新增 `tests/test_migration_gpu_launcher.py` 的 11 项无 GPU 控制覆盖多卡请求顺序、CPU 不查询 GPU、身份解析拒绝路径以及 CPU/GPU 的 proc 挂载分支。执行中没有加载 Torch、CUDA 或模型。

首次控制有 2 失败、9 通过，原因是测试夹具依赖最小私有 CPU sysroot 中不存在的 `mktemp`；仅为夹具补充临时目录创建和清理程序后，11 项通过，产品实现未因此调整。宿主 `python3` 没有 pytest，实际控制使用项目私有 CPU Python。

限定 Ruff 首次因只读项目中的 cache 写入被拒而未完成；禁用 cache 后通过。两个 shell 脚本语法检查通过。未重复整仓测试或上一轮实际 9B 短生成。

部署后分别进行一次 CPU 入口及一次 GPU3 命名空间入口核验，不调用 CUDA、不加载模型。CPU 实际观察到空 CUDA 设备列表及 `/proc ro`；GPU3 实际观察到 `CUDA_VISIBLE_DEVICES=GPU-7e01944c-768c-2f33-d58e-85d9b62ee185`、物理证据 `3` 以及 `/proc rw`。这些结果证明入口部署和身份映射，不等同于本轮正式推理已开始。

## 资源与 Docker 盘点

只读快照见 [host-inventory.json](../../artifacts/software-panel-v053/runtime-adaptation/host-inventory.json)。根盘仅约 3.4 GiB 可用，`/data0` 约 1.9 TiB 可用。默认 Docker 29.3.1 的数据目录为 `/var/lib/docker`，共享 daemon 有 2 个容器，其中 1 个运行；现有镜像没有 SWE-smith 官方镜像。本轮不得向这个根盘 daemon 拉取任务镜像。

建议正式环境使用独立 `/data0` Docker daemon，显式指定私有 `data-root`、`exec-root`、`pidfile` 和 Unix socket。其 containerd 也必须独立，不能复用 `/run/containerd/containerd.sock`。推荐禁用该私有 daemon 的桥接和 iptables 修改，容器按协议使用无网络运行；镜像拉取由宿主 daemon 完成。所有 Docker 客户端必须显式使用本轮 `DOCKER_HOST`。这些是给后续环境实现的接口要求，本子任务没有启动 daemon、修改共享 daemon 或拉取镜像。宿主 `sudo -n` 可用；rootlesskit、slirp4netns 和 subuid/subgid 映射已有，但 `newuidmap` 不在 PATH，不能据此宣称 rootless Docker 已准入。

盘点时 GPU3 空闲 21,896 MiB，其他 GPU 空闲 4,291—9,497 MiB，均不能容纳上一轮约 35.1 GiB 的 FP32 短生成峰值，更未满足原有准入余量。此为瞬时资源观察，不否认上一轮 GPU3 确实可用；后续调度应继续按既定容量门等待，不改变精度、模型配置或借容量不足时冒险启动。
