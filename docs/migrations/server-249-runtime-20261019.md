# 249 迁移的私有运行时（2026-10-19）

后续状态：用户已选择保留宿主内核并适配项目。当前执行器使用独立命名空间后端，有限 CPU 控制通过；私有运行时另补了四个与原字节一致的版本化库文件名。详见[项目适配说明](server-249-project-adaptation-20261019.md)。下文保留迁移时的原验收与限制，原冻结执行器没有被回写或重新评分。

本说明只涉及服务器迁移。原实验、原模型参数、冻结源码、输入、报告和停止记录均保持；迁移不授权恢复旧队列，也不将一次导入检查描述为实验复现。

## 已核实的差异

源机为 Ubuntu 24.04.1 x86_64，主模型与 CAL2/v052 CPU 环境依赖系统 Python 3.12.3，源 GLIBC 为 2.39。目标 `120.133.75.249:10022` 为 Ubuntu 22.04.4 x86_64，内核 `5.15.0-186-generic`，系统 Python 为 3.10.12，GLIBC 为 2.35。目标未发现 `bwrap` 或 `proot`；一次 `unshare --user --map-root-user --mount` 控制已确认非特权用户和私有挂载命名空间可用。

因此，不把源 `/usr/bin/python3.12` 直接链接到目标系统 `/usr`，也不替换目标 libc。项目中的虚拟环境、历史源清单及其绝对路径保持原字节。

`.venv` 另依赖源 Conda Python 3.14.6，以及源用户 Python 3.14 site-packages 中的 pytest 9.1.1、ruff 0.16.4；这些由主迁移全量复制。模型 resident 环境实际使用 torch 2.6.0+cu124、transformers 5.17.0、peft 0.18.1、accelerate 1.15.0；不能按当前 `pyproject.toml` 的旧 `transformers<5` 约束重新安装后声称保留了冻结环境。

## 隔离布局与启动

私有包位于 `/data0/zhuxinrui/proworksim-runtime`。`build_runtime.py` 只在一个新目录内打包源 Python 3.12、完整标准库、动态加载器、标准库扩展所需动态库、libstdc++/libgcc/libseccomp，以及基础业务工具。`manifest.json` 记录来源文件 SHA256、大小、源平台和工具清单。原目录不被修改。

原 shell 执行器固定调用 `/usr/bin/bash`，原 mini 执行器固定调用 `/usr/bin/git`；二者连同 `/bin/sh`、`env`、`rg`、`timeout`、`patch/diff`、`make`、常用文件/文本处理、归档及进程查询命令均已纳入，Git 的 helper/template 树和新增 ELF 的动态库闭包一同复制。这些来自源宿主系统，保持与源 Python 一致的用户态基础；不把“最小包”缩减成只能导入 Python。

`run-cpu.sh` 在一个新的非特权 user/mount namespace 中，把私有 sysroot 作为子进程根目录。目标宿主的 `/usr`、Python、加载器和动态库均不改动。项目、Conda、用户 site 和历史模型目录只在该命名空间内挂载到原来可解析的路径。默认只读项目，独立临时目录可写；`--write-project` 才允许新命令写项目。

命名空间内部的 `/data1/zhuxinrui/...` 与 `/data0/zhuxinrui/...` 分别直接绑定同一目标 `/data0` 实体，因此通过旧路径访问时 `realpath`/`Path.resolve()` 仍保持旧 `/data1` 身份。原用户 site 也直接绑定到原 `/home/zhuxinrui/.local/...`。这是进程局部的路径布局，宿主软链接和物理存放位置不改变。

已迁移的 `/data0/zhuxinrui/.cache/huggingface` 只读挂载到原 `/home/zhuxinrui/.cache/huggingface` 以及 `/data0`、`/data1` 对应位置。现有缓存可见；本次不下载新缓存，不增加可写缓存策略。`--write-project` 的语义仍只涉及项目目录。

默认只挂载 `/dev/null`、`zero`、`random`、`urandom`，不提供 NVIDIA 设备；同时清空 `CUDA_VISIBLE_DEVICES`。命名空间仍共享目标内核与网络；UID 在该 user namespace 内映射为 0，宿主身份仍为原用户。这是迁移兼容层，不是新的实验沙箱。

```bash
/data0/zhuxinrui/proworksim-runtime/run-cpu.sh \
  /data1/zhuxinrui/projects/ProWorkSim/.venv/bin/python -B \
  scripts/migration_249_runtime/verify_cpu.py

/data0/zhuxinrui/proworksim-runtime/run-cpu.sh \
  /data1/zhuxinrui/projects/ProWorkSim/runs/v016-sdk/resident-venv/bin/python -B \
  scripts/migration_249_runtime/verify_cpu.py \
  --packages proworksim openpyxl duckdb torch transformers peft accelerate
```

若需要在新批准任务中使用原 v030 依赖覆盖，可显式传入 `/usr/bin/env PYTHONPATH=/data1/zhuxinrui/projects/ProWorkSim/runs/v030-runtime-deps:/data1/zhuxinrui/projects/ProWorkSim/src`，随后才是所选解释器命令。此处不启动该类任务。

## 显式 GPU 入口：已准备，尚未运行验证

主迁移的一次只读 `nvidia-smi` 记录目标为 **8 × NVIDIA A800-SXM4-80GB，驱动 580.178.04**；本环境子任务没有重复查询或创建 GPU 上下文。

`run.sh --gpu 0,1 -- COMMAND ...` 是为未来明确授权任务准备的入口。物理设备编号必须显式给出；无 `--gpu` 时保持 CPU。GPU 分支仅绑定所选目标 `/dev/nvidiaN`、目标 NVIDIA 控制节点及只读 `/sys`，并设置相应 `CUDA_VISIBLE_DEVICES`。通过目标 `ldconfig` 的 x86-64 条目取得 `libcuda.so*`、`libnvidia-*.so*`，将这些目标驱动库单独挂载到 `/opt/host-nvidia`，不会把目标整个 `/usr/lib` 加入搜索路径，不覆盖私有 GLIBC 2.39，也不迁入源主机驱动。目标同时存在 32 位驱动条目，入口明确不选用。

本轮只准备此入口并检查 shell 语法，**未执行 GPU 分支、CUDA 测试、训练或模型生成**。因此目标 CUDA 实际运行能力尚未被本次迁移实测；不能仅根据型号和驱动号宣称原数值路径复现。MIG、图形显示、编译工具链等不在此最小入口的已验证范围。

若目标存在 `/usr/bin/nvidia-smi`，GPU 分支还会把目标二进制只读挂入该路径，供未来已授权监督器使用；此二进制同样不从源机搬运。本轮没有通过私有 GPU 入口执行它。

## 已证实的宿主内核限制

一次只读 `landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION)` 查询返回 **ABI 1、errno 0**。冻结的 `src/proworksim/software_calibration_shell_v051.py` 要求 **Landlock ABI ≥ 3**，否则明确拒绝安装隔离。因此当前目标 kernel 5.15 不满足该 OH/reference shell 和测试执行器的前置能力。

私有 GLIBC/Python 不能改变宿主 Landlock ABI；此处不弱化原规则，不热改冻结源码，也不偷偷升级或重启共享宿主。要在目标上运行这些原执行器，需要另行完成具备所需 Landlock 能力的目标内核部署，或按新授权协议设计并审计替代隔离实现。数据与用户态环境迁移完成不能被表述为这些执行器已可运行。

## 验收范围与限制

迁移只需确认必要解释器可启动、原路径可解析，以及必要包可导入。`verify_cpu.py` 不调用 pytest，不创建模型或 tensor，探针代码不显式查询 CUDA，不进行训练或评估。CPU namespace 中无 NVIDIA 设备。验收结果另存迁移回执。

私有基础 Python 已完成一次目标启动：Python 3.12.3、GLIBC 2.39、OpenSSL 3.0.13、SQLite 3.45.1，`ssl/sqlite3/bz2/lzma/zlib/ctypes` 导入通过。回执为 `/data0/zhuxinrui/proworksim-runtime/base-python-import-receipt.json`；主数据复制完成后未重复这项标准库控制。

## 主同步后的真实验收终态

两个项目分片及外部依赖完成后，唯一整树 `rsync -aH --no-inc-recursive` 收尾返回 **0**，清单为 912,556 项、343,300,126,724 逻辑字节。本说明不重复执行整树、checkpoint 或权重校验；主迁移报告负责运输与最终差异收口。

首次 CPU 路径/工具预飞在进入私有解释器前失败，返回码 **32**，原因是目标 `/proc` 含 `binfmt_misc` 子挂载，rootless 非递归 bind 被内核拒绝。原失败 stdout/stderr 与诊断均保留。只修改迁移 `enter-namespace.sh`：对内核文件树使用递归 bind 保留子挂载，并将顶层挂载设为只读、保留 `nosuid/nodev/noexec`。独立挂载诊断通过后再执行实际验收；原虚拟环境、冻结源码、实验数据及宿主系统均未修改。GPU 分支对应 `/sys` 也采用该挂载方式，但 GPU 分支仍未执行。

第二次验收的 **5 项全部返回 0，stderr 均为空**：

| 检查 | 实际结果 |
| --- | --- |
| 路径与基础工具 | 旧 `/data1` 及 `/home/.../datatmp` 路径解析保持旧 `/data1` 身份，与新 `/data0` 指向同一实体；项目和 HF 缓存只读，原 HF 缓存路径可见；namespace 内 NVIDIA 字符设备为 0。Bash 5.2.21、Git 2.43.0、rg 14.1.0、timeout 9.4、Make 4.3、patch 2.7.6 的版本命令全部成功。 |
| 实际 `.venv` 导入 | Python 3.14.6 / GLIBC 2.39；`proworksim`、openpyxl 3.1.5、duckdb 1.5.5、pytest 9.1.1、ruff 0.16.4 成功导入。后两者确实来自原用户 site。 |
| CLI | 原 `.venv/bin/proworksim --help` 正常返回帮助文本。 |
| 实际 resident 环境导入 | Python 3.12.3 / GLIBC 2.39；`proworksim`、openpyxl、duckdb、torch 2.6.0+cu124、transformers 5.17.0、peft 0.18.1、accelerate 1.15.0 的 CPU 导入成功。 |
| 实际 CAL2 环境导入 | 原 CAL2 CPU venv 的 Python 3.12.3 与 pytest 7.2.0 成功导入；没有执行 pytest 测试。 |

同次路径验收仅取得 `.env`、项目 Qwen3.5-9B 模型根、外部 `Qwen2.5-7B-Instruct-a09a35458c702b33eeacc393d103063234e8bc28` 根的存在性、类型、解析路径与权限元数据，均存在。`.env` 为普通文件、原样迁移的模式为 `0664`；两个模型根为目录、模式 `0775`；目标宿主 owner/group 为 `1021/1022`。未读取 `.env` 内容，未加载或 hash 模型权重，不另扫 checkpoint 树。

`.venv` 既有 distribution 元数据仍为 `proworksim 0.2.0`，CLI 既有帮助字符串仍显示 `v0.11.0`；实际导入源为 `/data1/zhuxinrui/projects/ProWorkSim/src/proworksim`。这些源端既有版本文本没有在迁移中被归一化或改写。

原始回执已从目标复制回 [runtime 证据目录](../../artifacts/server-249-migration-20261019/runtime/)。其中 [首次预飞](../../artifacts/server-249-migration-20261019/runtime/cpu-verification-20261019-attempt1/summary.json) 保留失败，[最终五项](../../artifacts/server-249-migration-20261019/runtime/cpu-verification-20261019-attempt2/summary.json) 与各 stdout/stderr、命令驱动原件独立保存；[敏感文件与模型根元数据](../../artifacts/server-249-migration-20261019/runtime/cpu-verification-20261019-attempt2/asset-path-metadata.json) 不含文件内容。首次复制的 23 个小证据文件共 290,879 字节，包含用户态来源 manifest；约 140 MB 的私有运行时 payload 没有纳入仓库证据。

本阶段模型调用、GPU 分支、训练、参数更新、pytest 测试和全仓静态检查均为 **0**。仅新增脚本目录的 Ruff 与 shell 语法检查已通过；CPU 验收通过后不再次复跑。上述结果证明迁移入口的有限 CPU 可运行性；前文已确认的 **Landlock ABI 1 < 3** 限制仍然存在，原 OH/reference 执行器的业务运行并未因此被宣称通过。

源 v052 runtime 清单还约束系统库与 Python 树哈希。私有包提供源用户态文件，但目标内核版本、namespace 身份、硬件和后续驱动可能不同；因此这里不宣称原科学执行身份完全相同。未来真实运行仍需按新任务的有限准入规则记录目标宿主差异；原报告不改写、旧未知不填零。

本私有包不包含系统编译工具链、任意宿主命令、完整字体服务或源 GPU 驱动。需要这些能力的新任务须明确补充运行依赖，不能把最小导入通过当作全部功能通过。
