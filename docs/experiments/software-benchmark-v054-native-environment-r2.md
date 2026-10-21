# v054：真实原生环境、共同资源限额及官方评分接缝修复

日期：2026-10-21，Asia/Shanghai。用户要求尽快修复并完成三组实验准备。本报告记录已实际执行的 CPU 环境适配，不记录正式模型成绩，不启动训练。旧 scorer r3、原首题 `technical_unknown`、此前合成控制与失败回执均保留。

## 1. 本轮已经闭合的部分

固定首题仍为 `astropy__astropy-12907`，未按结果换题。

- 从已核实的共同 Actor 派生镜像导出真实 rootfs，保持其完整代码、公开构建物、原始数字 UID／GID 和文件模式。
- 原生官方工具在真实任务根内成功启动，使用镜像的 Conda Python 3.9.20；Astropy 导入位置在 `/testbed`。
- 原生执行进程及其 controller／公开测试进程可纳入同一个项目独立 system slice。内核实际限额为 4 CPU、16 GiB、16384 pids，模型服务另计。
- 首题一次新版本官方 CPU 评分完成，产生可信官方报告；空候选为 unresolved，**不计任何模型失败或完成率**。

三组端到端 runner 的合成 CPU 验证由独立 runner 报告记录，本报告不提前替该工作宣布成功。首题真实 native 控制也不等于全部 500 份 rootfs 都已展开或每个仓库测试全部执行过。

## 2. 原基线错误与版本化修复

旧首题控制已经成功创建并启动 Docker 容器，但本地准备包装要求 `HEAD == dataset base_commit`，在官方 eval 开始前失败。实际官方 HEAD 为 `d350420dae50c80ca33b845734c31428d62af0a8`，数据 base 为 `d16bfe05a744909de4b27f5875fe0d4ed41ce607`。

并行的共同初态审计确认前者是 SWE-bench 的 setup 提交：其唯一父提交为数据 base，作者 `SWE-bench <setup@swebench.com>`，主题为 `SWE-bench`。Astropy 包含 1861 项文件模式变更，其中只有 `pyproject.toml` 内容对象不同。官方 5.0.2 实际 `run_instance` 直接在该镜像初态应用候选，不在启动时整树 reset 到数据 base。因此强制 HEAD 相等会拒绝官方准备后的合法初态，直接 reset 也可能破坏构建条件。

新 `software_benchmark_scorer_r4_v054.py` 保留未修改的官方 5.0.2 评分器，也保留旧 r3 包装。它新增可信基线映射：

| 身份 | 首题实际值 |
| --- | --- |
| 数据 base commit | `d16bfe05a744909de4b27f5875fe0d4ed41ce607` |
| 数据 base tree | `4d9ea46e57a9bc539b358a59c526dfd933f98aba` |
| 官方 setup HEAD | `d350420dae50c80ca33b845734c31428d62af0a8` |
| 官方 setup tree／共同 Actor tree | `507f65ecab7408b900788d937fdad20e5b4e87b8` |
| 隔离后的 Actor 根提交 | `e572af97883068a33564cf787411074705963f7b` |
| 官方评分 image ID | `sha256:9b1cabf7bcd83a28469f67e3852d8e2207e90d45aa71f436bb7e600bdee8bae2` |
| 派生 Actor image ID | `sha256:b3b91f6a3e1d4a99e72fb3ff225a8e167d29716e2702bcffb471c4efbd6a1728` |

映射包含 task、原 manifest/config、setup 关系、Actor tree 等值、Git 隔离与实际 Python 资格；整体文件 SHA 进入评分身份。每次评分容器启动后实际核对原官方 setup HEAD、tree 和 clean 状态，再应用补丁和执行官方脚本。不是简单删除旧断言，也不把 Actor 的新 Git 根当作原官方评分提交。

REF／MATCH 正式评分还要求 `native_candidate_lock`，核对已闭合槽的 arm／task、唯一 patch、base／candidate 完整树。PROJECT 保持原有 code／delivery 双端点锁。不同映射、包装、条件、候选或 attempt 产生不同 run ID，旧缓存不复用。

新增映射控制仅测该变化：合法 setup 身份且 Actor tree 同值可通过；错 image、错 tree 或未识别 setup 关系拒绝。结果 **1 passed，0.06 秒**。没有重复旧 500 个 TestSpec 或整套单元控制。

## 3. 真正保留镜像 UID／GID

首真实 rootfs 有 74,323 个归档项、2,849,817,097 字节普通文件，包含 9 种 UID／GID 对。除 `0:0` 外，实际存在 `1000:1000`、`100:0`、`0:42` 等；把所有文件改为当前用户所有不能被称为数值权限等价。

当前用户已有明确的 `sudo -n` root bootstrap 能力及 `/etc/subuid`／`/etc/subgid` 的 `558752:65536` 范围。因此没有安装 newuidmap，没有下载或增加全局 setuid 程序。新增静态 `native_uid_bootstrap_v054.py` 只执行以下有限操作：

1. 在项目新准备目录内按 manifest 的原 UID／GID 应用数值映射；路径逐级使用 directory fd 和 no-follow，不能跟随归档链接操作宿主外部文件。
2. 建立新 user namespace：UID 0→宿主 1021，GID 0→宿主 1022；内部 1…65536→现有 subordinate 范围。范围外身份明确拒绝。
3. 映射写入后 bootstrap 父进程立即降回原普通用户；SDK 导入发生在独立后续 worker 内。
4. 为新的 episode 安全执行 `cp --archive --reflink=auto`，保持映射属主和权限，拒绝覆盖已有目标目录。

worker 启动时核对实际 uid_map／gid_map 与 manifest 一致，之后仍执行私有 PID／mount／network、chroot、全部 capability 清零、no-new-privileges 和 non-dumpable。宿主 SDK、resident 及现代目标包源码不挂进任务根。三组公开执行使用相同 image 派生根；原官方评分 image 不改。

`clone_prepared_rootfs(environment_manifest, destination)` 为每个 episode／PROJECT 公测建立独立初态，不共享先前补丁或测试反馈。模板资格和每次 clone 的身份链分别保存。CPU 真实资格控制使用模板的独立副本，未修改模板代码树。

入口：

```bash
PYTHONPATH=src .venv/bin/python tools/prepare_native_rootfs_r2_v054.py \
  --public-tasks <固定完整500题公开投影> \
  --public-tasks-sha256 <投影SHA> \
  --mapping <该题actor-admission-r2.json> --mapping-sha256 <映射SHA> \
  --docker-socket unix:///absolute/private/docker.sock \
  --output <新的native-rootfs目录>
```

`run_native_worker_mapped_v054.sh` 保持 `--rootfs --stdlib --environment-manifest` 参数，正式根必须通过真实资格；准备控制可显式使用 `--preparation-only`。单题 rootfs 按实际需要展开和缓存，不复制 500 份重复环境来伪造就绪数量。全部题的共同镜像／映射库存由镜像准备报告负责。

## 4. 一个共同资源上限，及被拒绝的更大范围操作

第一次检查发现 user manager 只委派了 memory／pids。虽然 systemd 显示 CPUQuota=400%，其内核 cgroup 没有 `cpu.max`，不能声称 CPU 限额已生效。直接设置 DelegateControllers 在本机旧 systemd API 不受支持。

随后申请修改当前用户的运行时 user@ 委派，被自动审批拒绝，理由是系统级 drop-in、daemon-reload 和共享祖先 cgroup 的影响范围超出项目专属验证；**该操作没有执行**。没有用间接命令绕过拒绝，也没有停止其他会话。

实际采用并获准的更小范围方案是项目独占 system slice：

`/proworksimv054ep<episode_claim>.slice`

固定 `native_resource_helper_v054.py` 只创建或释放这个严格命名、绑定 claim 的临时资源域；不修改 user@、不重载 systemd、不改其他用户的限额。controller、native worker 和 PROJECT 固定公开测试的独立 worker 均在其下，以原宿主用户运行。根监督器记录每个服务的实际 invocation／PID／cgroup；模型服务不在这个 Actor 预算里。

| 内核文件 | 实际值 |
| --- | --- |
| `cpu.max` | `400000 100000` |
| `memory.max` | `17179869184` |
| `pids.max` | `16384` |

先用两个短暂普通用户子服务验证同一父域，再在真实原生工具控制中核对。它们共享一个聚合上限，不是每份 controller／worker 各获得 16 GiB。释放前要求整个父域 populated=0，随后 stop／revert 自己的临时属性。

监督器的关闭规则保持：官方 terminal.close 返回后的 ack 不等于进程树已静止；必须完成宿主服务停止／reap／cgroup 空证明，再锁候选。

## 5. 活跃 Docker 子挂载与私有 runtime 修复

真实控制初次启动失败于进入私有 Python 前。项目目录内当时有 14 个活跃 Docker overlay 子挂载，旧 trusted runtime 用非递归 `mount --bind` 绑定整个项目；在 user namespace 内丢弃这些受保护子挂载被内核拒绝，退出码 32。

新增 repo 内版本化 `enter_benchmark_runtime_v054.sh`，仅将项目目录绑定改为 `--rbind`。Actor 最终 chroot 边界不变，这些可信启动阶段挂载不会进入任务根。原 `/data0/zhuxinrui/proworksim-runtime` 脚本没有修改。

`run_benchmark_runtime_v054.sh` 保留原 `--write-project [--gpu physical-index]` CLI、物理卡到 UUID 的验证及显式设备约定；默认仍 CPU。native mapped worker、SDK controller 和新 scorer 统一使用修订入口。CPU 启动控制实际通过；本文没有据此宣称 GPU 模型加载通过。

旧 r4 service 和 native-image r1 都停在 mount 启动阶段，没有进入 Python／工具／官方测试；失败记录保留。修复后只继续未完成的必要控制。

## 6. 实际真实控制结果

真实 native 控制 r2 于 **09:23:27–09:23:40 CST** 完成，模型／GPU 调用均 0：

- 官方 Terminal、FileEditor、TaskTracker 成功构造在任务 rootfs 内。
- Python executable 为 `/opt/miniconda3/envs/testbed/bin/python`，公开 Astropy 从 `/testbed` 导入。
- 从每种实际 UID／GID 对选择一个公开路径，共 9 类，内核返回数值与原 archive 一致；全部 74,323 项已由可信映射阶段逐项应用并记录。
- Git HEAD／tree 与 Actor 映射一致；127.0.0.1 收发成功；网络接口只有 lo。
- 宿主 worker／SDK 源码路径在 FileEditor 中不可读。
- capabilities 全零、non-dumpable、NNP、PID 1、无 NVIDIA 设备维持。
- 关闭后外层进程退出 0、服务 cgroup populated=0，父资源域成功清理。

新 scorer r4b 于 **09:24:17 CST** 完成原先固定首题的空候选官方评分：`official_scoring_status=official_report`、`baseline_resolved=false`、`counted_as_model_result=false`。实际保存了 test output 和 report，容器 stop／remove 成功。空候选不修复缺陷而 unresolved 是环境控制观察，不是 Qwen 能力结果。

官方隐藏脚本、测试输出、测试标识及完整报告仍仅在 trusted `official-output`；公开准备回执只发布控制状态、身份 SHA、时间和资源行为，不把评分反馈给 Actor。

固定 r4 安装 manifest：

`artifacts/software-benchmark-v054/scorer/installation-manifest-r4.json`

SHA256：`2b6c04d1ca7e9345012af532764037c1e976fc9ff45725b108db0cd33edc63a1`。

统一准备汇总为 `artifacts/software-benchmark-v054/native-environment/preparation-r2.json`。旧 user-slice CPU 未生效记录、被拒绝操作、native-image r1 启动失败、首题旧 technical_unknown 与新的成功回执按各自范围保留，不合并为同一次成功。
