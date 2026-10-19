# 服务器 249 的项目执行器适配（2026-10-19）

## 范围与实施选择

用户先要求处理迁移报告中的 Landlock 限制，随后明确要求“让项目对当前服务器做适配”。本轮采用项目执行器适配，保留宿主 Ubuntu 22.04 / Linux `5.15.0-186-generic`，不安装新内核、不修改 GRUB、不重启、不恢复已暂停的实验库存。

前期已读取内核、驱动、启动配置和包依赖，并成功刷新 APT 索引；两次 HWE 安装模拟均为 8 个新包、0 升级、0 删除，没有执行安装。读取权限最初受工具沙箱的 `no_new_privs` 限制；在获准的宿主只读操作中确认账号具有 sudo 权限。此权限没有用于升级内核。GPU 查询只取得既有计算进程和显存元数据，没有创建 CUDA 上下文、装载权重或终止进程。

旧迁移报告中 ABI 1 的事实与原执行器 ABI ≥ 3 的要求仍成立。新后端不把 ABI 数字改成 3，也不将缺少 `TRUNCATE` / `REFER` 的 ABI 1 当作相同接口。

## 文件系统与系统调用边界

当前源码在启动工作子进程前冻结 `filesystem_policy`，记录实际 Landlock ABI、选择的文件系统后端及新后端源码引用。ABI ≥ 3 的宿主继续使用原 Landlock 文件系统策略；当前宿主选择独立的用户/挂载命名空间后端。子进程执行前重新核对能力和源码，发生变化即拒绝执行。

新后端在原 Python 子进程内安装隔离，保留 PID、会话、父进程登记、已初始化 pytest 状态及宿主明确声明的预连接 socket。它构造最小根目录，只绑定工作树和声明的只读运行依赖，不暴露宿主 `/proc` 或 `/sys`；根目录和路径脚手架只读。可写工作树保留正常创建、写入、截断、删除和跨目录移动；只读执行器的工作树也以只读方式挂载。

挂载完成后收回能力并禁止获得新权限，随后执行原 seccomp 与资源限制。新建网络连接、跨进程控制、重新挂载、切换根及创建新命名空间仍受限制；另明确拒绝 `mknod` / `mknodat`，使可写工作树不能因更换文件系统后端而新增 FIFO 或设备节点能力。不能成功安装这些限制时，不执行候选命令。

一次私有运行时结构探针得到：外层 UID 映射为 `0 → 1021`、长度 1；再次创建用户命名空间返回 EPERM，新建挂载命名空间成功；对 `chroot` 内非挂载点的 `/` 执行递归私有化返回 EINVAL。实现必须区分普通宿主用户与已有受限用户命名空间，不能将这些失败当作放弃隔离的理由。

技术依据：[Landlock ABI 与截断权限](https://docs.kernel.org/6.8/userspace-api/landlock.html#filesystem-flags)、[Linux 用户命名空间](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)、[挂载与只读 bind](https://man7.org/linux/man-pages/man2/mount.2.html)。仅 `chroot` 本身不构成完整隔离；本实现还依赖最小挂载集合、外部文件描述符限制、能力回收和 seccomp。

## 执行入口与历史身份

适配范围包括当前软件只读评分器、受限 shell、CAL2 独立测试子进程及 HOLD 独立测试子进程。v052 桥接另用显式新运行清单绑定当前实现和内核；旧清单及固定 SHA 的验证分支保留，不把新后端的回执混入旧实验身份。

Python、系统库和 CPU 测试依赖继续使用已迁移的私有运行时。不得直接用宿主 Python 3.10 替代原 CAL2 Python 3.12，或按旧 `pyproject.toml` 重新安装模型环境。

## 验证记录

有限 CPU 验证已完成。原始 JSON、stdout、stderr 与合成控制源码保存在 [本轮证据目录](../../artifacts/server-249-adaptation-20261019/)。本次不运行全仓 pytest，不重验旧业务题、权重、checkpoint 或已通过的整树迁移库存。

| 控制 | 实际结果 | 范围 |
| --- | --- | --- |
| 文件系统、系统调用与 socket fixture canary | 第二次 28/28 通过 | 工作树读写、截断、跨目录移动；只读文件保护；外部路径、symlink、proc 逃逸和新建网络拒绝；预连 TCP 与匿名 socketpair 可用 |
| 当前 shell 与 CAL2 测试子入口 | 各 1 个合成 pytest 节点通过 | 原 CPU Python 3.12 环境；CAL2 输入文件保持 |
| HOLD 独立子入口 | 1 个合成 native unittest 节点通过 | 原 Python 3.10 环境；只覆盖实际子入口，不重做整个 HOLD 父清单资格或旧题 |
| 通用只读评分器 | 合成驱动通过 | 候选读取成功，写入、截断和 fork 拒绝 |
| 声明、FD 与来源改变控制 | 最终相应控制通过 | 拒绝重叠路径、宿主 proc/root、嵌套挂载、继承目录/普通文件、策略篡改和可写随机设备 FD |
| v052 新运行身份 | 8 项身份合同通过 | 新旧身份分离、源码/环境漂移拒绝，原分支继续要求原 SHA |
| 新运行清单的真实桥接 | 1 个新合成 pytest 节点通过 | 当前 `run_repository_tests`、独立清单和实际 CPU 子进程；不运行六道历史 CAL2 题 |
| 变更文件 Ruff | 通过 | 只检查本轮涉及的源文件、脚本、测试和合成控制脚本 |

专属 pytest 文件共有 6 个不同测试函数，按失败与实际变更定向重跑，最终每项对应控制通过；不是一次全文件 6/6 的记录。四次执行分别为 `3 failed / 2 passed`、`1 failed / 2 passed / 2 deselected`、`1 failed / 1 passed / 4 deselected`、`2 passed / 4 deselected`。初次错误和修订后的结果全部保留。

首次 canary 在执行命令前失败：O_PATH 源描述符在创建新挂载命名空间之前打开，bind 引用旧命名空间中的 mount，返回 EINVAL。修订为先隔离挂载空间，再打开并固定源对象；随后 28 项通过。

HOLD 最初因 Python 3.10 缓存的只读 `/dev/urandom` FD 被拒。实现只允许字符设备 `rdev=1:9`、访问模式 `O_RDONLY` 且非 `O_PATH` 的运行时 FD，并单独记录 `runtime_readonly_device_fds`；预连接网络 FD 仍由原显式 fixture 声明。写入、读写、O_PATH 随机设备描述符及普通只读文件继续拒绝。一次独立脚本/runpy 对照没有观察到源脚本 FD，因此没有据猜测放行源码描述符。

新增 FD 控制的首次运行误用了父环境 Conda Python 3.14，观察到它保留的 `libffi` FD；这不是实际 CAL2/HOLD 子环境。控制改用实际 CPU Python 3.12，并要求错误精确指出被测试的 FD，随后通过。HOLD 本身在同轮已通过，不因控制脚本问题重跑。

28 项 canary 对应的后端 SHA 为 `4fd0c17a003c9022f3be86c9720d1a3108264781bc199bb19024c704ed30615d`。随后唯一后端行为修订是上述只读随机设备 FD 例外，最终 SHA 为 `46b327b600ccded8f8110d2f579e20e249bcbd27bf2d8d0d600e7838f642eadb`；复用既有 28 项结果，新增例外由窄 FD 控制、实际 HOLD 和新桥接控制核验，没有把旧回执改成最终源码哈希。

## 私有运行时的必要补全

首次准备新 v052 清单时，原清单引用的 `/usr/lib/x86_64-linux-gnu/libseccomp.so.2.5.5` 不存在。迁移打包器将原库字节复制到了 SONAME 文件名，未保留所有原版本化名称。新增 `restore_library_aliases.py` 对原 8 个库逐一检查 SHA256 和大小，之后仅在私有 sysroot 中为以下 4 项建立同文件硬链接：

- `libseccomp.so.2.5.5`
- `libexpat.so.1.9.1`
- `libz.so.1.3`
- `libffi.so.8.1.4`

现有库内容、宿主 `/usr`、NVIDIA 驱动均未修改；未扫描 Python 整树。首次失败和[实际补全回执](../../artifacts/server-249-adaptation-20261019/library-aliases.json)保留。第二次清单准备成功，保留原解释器和依赖声明，并明确记录本轮未重做整树 hash。新清单路径为 [bridge-runtime.json](../../artifacts/server-249-adaptation-20261019/bridge-runtime.json)。

迁移的 Ruff Python 包存在，但其可执行文件未被复制。已在项目忽略目录 `runs/server-249-tools/ruff` 安装同版本 `ruff==0.16.4`，并以 `.venv/bin/ruff` 相对链接接入。项目标准 `.venv/bin/python -m ruff` 已实际完成本轮限定检查，没有修改系统 Python 包或模型依赖。

## 使用方法及结论边界

现有私有 CPU 启动入口继续使用。以下命令是今后重新准入时的操作入口，不要求在已通过的本轮重复执行：

```bash
/data0/zhuxinrui/proworksim-runtime/run-cpu.sh \
  /usr/bin/python3.12 -B scripts/migration_249_runtime/verify_server_sandbox.py

/data0/zhuxinrui/proworksim-runtime/run-cpu.sh --write-project \
  /data1/zhuxinrui/projects/ProWorkSim/.venv/bin/python -B \
  scripts/prepare_server_bridge_runtime_v052.py --output <新的清单路径>
```

新运行清单绑定当前源码和内核；相关源文件改变后需创建新的清单，不改写已发布清单。当前库别名补全可由 `restore_library_aliases.py --apply` 在私有 sysroot 中按原字节检查后复现；已存在且相符的条目不重写。

结果证明当前服务器上的有限 CPU 隔离与合成执行路径可用。最小根目录、可见宿主信息和系统调用失败形式与原 Landlock 路径不是逐字节相同协议，因此 v052 使用新执行身份。旧冻结源码、原资格、旧未知结果、暂停库存和费用记录均保持，不能将本轮视为旧实验复现或学习收益。没有 GPU 数值验证、模型生成、参数更新或自动后继；共执行 4 个新的合成业务测试节点，历史业务题重新评分为 0。
