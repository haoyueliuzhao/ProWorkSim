# v054：原生工具隔离、真实 SDK 绑定与镜像 rootfs 准备

日期：2026-10-20 至 2026-10-21，Asia/Shanghai。本文补充此前的 Actor 环境记录，属于数据与环境准备。所有控制均为合成 CPU 控制，模型调用、GPU 启动、实际 Verified 求解任务均为 0。本文不把先前冻结的 Actor／scorer 回执改写为已经通过新的检查。

## 1. 已经解决的具体接缝

实现了独立 native worker，并把它接入真实 OpenHands SDK 1.49.6 `Agent`／`LocalConversation`。REF 与 MATCH 共用相同工厂、相同官方 Terminal／FileEditor／TaskTracker，执行位置通过 JSON RPC 转到隔离 worker。未使用 v053 受限 terminal，也未增加 PROJECT 的任意 shell 入口。

实际双臂控制分别创建独立 rootfs、worker 和 SDK controller。两臂各完成 10 次真实工具调用；持久 PTY 跨调用保存 `cd`／`export`，FileEditor 完成多文件创建、替换及根目录内绝对路径读取，TaskTracker 保留计划。两臂五个最终工具（包括 SDK 的 finish／think）的模型可见 schema、说明、静态 system prompt 和 condenser 相同。没有调用 LLM。

SDK controller 中对三个宿主 executor 构造函数放置了仅限控制进程的失败探针，计数均为 0；真实工具 executor 只在 worker 中构造。文件修改出现在对应隔离根目录，读取宿主标记文件和宿主 SDK 源码均失败。工具内容由官方 observation 在 worker 内生成，再原样返回 SDK；不在宿主重做截断、路径展开或观察文件保存。

因此，**合成环境中的真实原生 Agent 工具隔离与传输已经验证**。这仍不是“500 题真实环境已准入”：官方镜像 rootfs、实际依赖、公测入口和资源限额资格另有必要门。

## 2. 运行边界

`tools/run_native_worker_cpu_v054.sh` 创建独立 user／mount／network／PID namespace，最终 worker 是其中的 PID 1。它是专用进程入口，不在已启动多线程 SDK 的父进程中执行 fork 后继续使用继承的 Python 状态。

可信阶段先导入固定官方工具及其必要 CPU 模块、编码表，并记录官方源码身份；尚未接收模型动作。随后：

1. 在任务 rootfs 内建立独立只读 proc、最小 dev、独立 devpts 和空 sys。
2. 挂入只含 Python 标准库的只读控制目录 `/opt/pws-control/python3.12`，不挂 resident、site-packages、requests 或 sympy。
3. 关闭额外文件描述符，chroot 到任务 rootfs，cwd 固定 `/testbed`。
4. 清除宿主环境和 Python 搜索路径，只保留明确的控制标准库路径。
5. 设置 no-new-privileges、non-dumpable，清空 effective／permitted／inheritable／bounding／ambient capabilities。
6. 在这个隔离根内调用官方 ToolDefinition 工厂，构造真正的 SubprocessTerminal 持久 PTY、FileEditor 与 TaskTracker。

worker 仅接受三个官方 action 的 JSON，或关闭操作；无 Python eval、动态代码装载或通用控制入口。Terminal 仍保留官方完整 shell 能力，但其文件、进程和网络视图受真实内核边界限制。FileEditor 仍允许读取任务 rootfs 中合法的绝对路径，没有偷偷缩成 workspace 路径白名单。

控制标准库是工具运行时新增文件；它没有目标仓库依赖副本，但不是原 Docker 镜像的一部分。正式任务实际资格必须记录这项环境差异，而不能把“来源于官方镜像”扩写成字节级完全相同的运行根。

SDK controller 本身保留可信依赖，使用独立 runtime 的 `/testbed` 绑定读取相同公开 checkout 元数据。模型工具通过 proxy 调用 worker，不能读取 controller 根目录、完整数据集、隐藏脚本、评分日志或宿主 Docker socket。controller 不是 actor 的执行根。

## 3. 镜像来源、环境与 UID 门

`tools/prepare_native_rootfs_v054.py` 是实际可执行的单题准备入口。输入是固定公开五字段投影、镜像 inventory、完整预检回执及官方 image config blob，沿用已经冻结的 Actor admission。它不读取 trusted-evaluation、gold 或隐藏 eval。

该入口要求本地 image ID 与 config blob SHA 一致，linux/amd64，baseline 和泄露预检已经通过。创建一个 `--pull never`、network none、cap-drop ALL 的停止容器；不启动仓库进程，随后通过私有 daemon 导出其文件系统。导出后立即清理自己的容器，不修改官方评分镜像。

归档写入独立新目录，拒绝绝对路径成员、`..`、重复条目及不允许的特殊文件。先写普通文件与 hardlink，最后创建 symlink；若归档试图经一个声明为 symlink 的父路径写文件，整份准备失败。因此归档中的绝对链接不能被宿主解包流程跟随到根目录之外。dev／proc／sys 由 worker 重建。保留逐项原始 mode、UID／GID、内容 SHA／链接目标和完整导出 archive SHA。

来源链形成：

`公开任务 + 实际镜像预检 → immutable image/config → export SHA → rootfs manifest → public environment manifest → worker ready`

`public-environment.json` 从该镜像原始 Config.Env／User 推导，显式选择预检确认的公有 Python 目录为 PATH 首项，并记录 Conda prefix。代理变量移除，GPU 可见性关闭；不继承宿主 PYTHONPATH、LD_LIBRARY_PATH 或 resident 路径。worker 要求此 manifest，并校验 rootfs manifest SHA、根目录路径、image ID 和原始 User 一致。它不会猜一个 Conda 路径作为全部 500 题的答案。

当前解包文件的实际宿主属主映射到私有 user namespace 的 root，而逐项原 UID／GID仅保存在 manifest 中。因此：

- `numeric_ownership_equivalence_admitted=false`；
- `native_real_task_control_passed=false`；
- official-image worker 默认拒绝正式运行，只能通过显式 `--preparation-only` 做 CPU 资格控制；
- 非 root 的镜像 User 和声明 volume 的镜像也会要求独立准备，不能静默降级。

这是真实的剩余准入限制，不通过放宽文件权限掩盖。服务器 `/etc/subuid`／`/etc/subgid` 已有 `zhuxinrui:558752:65536` 范围；当前命令搜索未找到 newuidmap／newgidmap。后续可以针对真实镜像需要使用该现有映射资源，本轮没有把未知情况表述为“服务器完全不支持 UID 映射”，也没有展开任意 UID 的兼容实现。

准备入口示例：

```bash
PYTHONPATH=src .venv/bin/python -B tools/prepare_native_rootfs_v054.py \
  --public-tasks /absolute/source/public-tasks.json \
  --public-tasks-sha256 <已冻结公开投影SHA> \
  --image-inventory /absolute/images/image-inventory.json \
  --preflight /absolute/images/preflight/<instance_id>.json \
  --image-config-blob /absolute/images/blobs/sha256/<config摘要> \
  --instance-id <固定500题中的ID> \
  --docker-socket unix:///absolute/private/docker.sock \
  --output /absolute/new-native-rootfs
```

截至本文控制完成时，尚未实际导出一个 Verified image rootfs；示例是可执行入口，不是已经执行成功的记录。三组实际使用同一基线及正式资源限制仍须由后续真实环境回执核对。

## 4. RPC 超时、关闭与候选锁定

`NativeToolRPC` 使用 fd readiness 和增量 `os.read` 读取完整 JSON 行；不再对半帧响应无限 `readline`。每次请求默认 6000 秒上限，也可传入剩余 deadline。超时后该 transport 标记失效，不能继续把迟到响应误配给下一次操作；外部监督器负责停止该 episode。

`close()` 的 `closed` 回执现在只在官方 `terminal.close()` 返回后发送，带：

```json
{
  "official_terminal_close_returned": true,
  "process_tree_quiescence_proven": false
}
```

这不是候选可以立即锁定的证据。外层 launcher 仍是宿主 session leader，worker 的 ready 中 PID 1 是命名空间内 PID。episode supervisor 必须登记实际宿主 PID／start ticks，在必要时独立于 RPC 锁终止会话，并等待 PID 1 与所有后台子进程真正退出，形成 quiescence receipt 后才能导出与锁定候选。三个 proxy executor 的各自 `close()` 不关闭共享 RPC；episode 在 Conversation 关闭工具后统一关闭一次。

worker launcher本身不配置 CPU／memory／pids cgroup。正式监督器须实施共同资源限制并留下证据，不能把本轮轻量 CPU 控制的成功当成 4 CPU／16 GiB／16384 pids 限额已生效。episode 生命周期、watchdog 和 closure 的实现与控制由独立模块记录；本报告不预先替它们宣布通过。

## 5. 实际必要控制与一次环境失败

| 控制 | 实际时间（CST）与结果 | 范围 |
| --- | --- | --- |
| 独立 worker r1 | 23:27:30–23:27:38，通过 | 12 次工具调用，持久 PTY、文件操作、宿主路径不可读、worker memory 读取失败、chroot 越界失败、未知 RPC 拒绝、退出 0 |
| 双臂 SDK binding r1 | 23:38:20–23:38:43，通过 | REF／MATCH 各 10 次真实 Agent 工具调用；可见 schema／说明／prompt／condenser 相同；宿主 executor 构造数 0 |
| rootfs／Env／身份门 | 3 passed，0.09 秒 | 链接逃逸拒绝、hardlink、原 UID/GID 记录、config SHA／Conda 环境、正式 UID 门与根身份检查 |
| 新回环与关闭控制 r2 | 23:54:44–23:54:49，bootstrap 失败 | 工具沙箱继承限制导致 `socket(AF_INET)` 返回 EPERM，尚无任何工具或模型运行 |
| 同一单臂控制 r3 | 23:56:20–23:56:31，通过 | 经自动批准在独立无外部网卡 namespace 运行；11 次真实 REF 工具调用，127.0.0.1 收发成功、有界 RPC、清理后 ack、controller／worker 退出 0 |
| 新模块／CLI／控制 Ruff | 通过 | 仅本次新增文件 |

r2 原件保留，未改为成功。r3 使用相同源代码，仅执行环境解除工具沙箱的 socket 创建限制；任务自己的网络命名空间仍只有 lo。127.0.0.1 是公开仓库测试可能需要的能力，不应因初始 lo 未启用而额外缩减原生接口。早期 r1 的外部连接拒绝也受工具沙箱影响，因此不单凭那次探针把拒绝原因全部归于 namespace；本轮实际命名空间和接口状态独立记录。

由于修改影响共享 transport／loopback／关闭路径，补测只跑 REF 单臂，未重复旧双臂等价性控制或全部评分控制。r3 的 `interfaces_identical=null` 表示本次没有重测双臂，不是把单臂结果填成新双臂证据。

本轮没有下载新的包、连接模型服务、读取模型权重或启动 GPU。合成 rootfs 中无真实 Verified 缺陷，也没有接收隐藏反馈，不能计为任何模型的完成率或稳定性。

## 6. 固定证据与剩余工作

稳定汇总入口：

`artifacts/software-benchmark-v054/native-worker/preparation-manifest.json`

其中 `sources` 固定新代码与控制脚本 SHA；`controls` 引用原始成功及失败回执；`status` 将合成工具边界、真实镜像资格、UID 等价、资源限额和正式模型准入分列。完整合成 RPC transcript、ready、公开文件及 SDK metadata 留在各自 `runs/software-benchmark-v054/native-*-control/`，小回执发布在上述 artifacts 目录。

尚待完成的实际资格包括镜像加载与完整预检、单题 rootfs 导出与同初态核对、数值 UID 映射等价、公开测试入口、公用资源限制、episode 实际闭合。无需为了这些等待项扩大架构、启动训练或先跑模型。已启动的一次性真实官方 CPU scorer 等待服务及其 r3 冻结评分器保持原状，见独立 scorer 准备报告。
