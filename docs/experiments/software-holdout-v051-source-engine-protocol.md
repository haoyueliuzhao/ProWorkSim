# v0.51 HOLD 来源与 CPU 执行层：内容访问前共同实现

本层独立于 CAL1/CAL2/r1/r2/r3。这里只用虚构材料开发和控制；不读取 HOLD 业务源码、问题描述、正确树、参考修复或真实测试正文，不执行其资格、SDK/tokenizer 或模型任务。固定 HOLD 八题和 32 条逻辑库存来自已冻结静态 metadata，不更换问题。最终用途唯一为 `held_out_checkpoint_evaluation`，`holdout_evaluation=true`，训练、Contribution、independent-confirmation 资格均 false。早先 `hold-source-design/memo.md` 的 purpose 是未执行设计提案，本文件及新模块替代该标识；保留原 memo 原字节。

## 冻结代码与接口

- `src/proworksim/repository_sources_holdout_v051.py`：`RepositorySources(source_root, *, runner=None, expected_manifest_sha256=None, allow_cpu_fixture=False)`。正式 provider 只载入已完成来源资格的合格子集。`case_spec/build_case/runner_spec/validate_files/run_public_tests/assess_files` 沿共同接口。模型初态只含原问题、完整 faulty 文件树及公开测试 ID union；F2P/P2P 分类和补丁不公开。所有原非生产文件均只读；固定 submit 仍由独立 world/collector 执行。
- `src/proworksim/software_holdout_repo_tests_v051.py`：`run_repository_tests(*, files, task, run_root)`。使用同目录冻结 `software_calibration_shell_v051.py`，不修改旧 runner。每个正式调用保留 input/spec/process/stdout/closed/result 原件；真实字节写读，CRLF 不正规化。
- `scripts/software_holdout_sources_v051.py`：显式 `--project-root`，只允许从 common snapshot 内运行。`export` 和 `qualify` 都先验证独立 release 与共同快照；导入脚本本身不访问材料。已进入的资格根拒绝重新执行，不能自动重试未决或按成绩另选题。

共同冻结必须包括全部新 provider/executor/exporter、world/collector、measurement/host、初态 SDK 测量脚本及其传递依赖，原 shell helper，控制摘要和 CPU environment-template。root 负责创建 `runs/software-holdout-v051-common/source` 与 common-freeze/release；本代理未创建或执行真实材料放行。

## CPU 环境与可读来源

原 Python profile 固定来源：`artifacts/software-calibration-v051/cal2-sources/metadata/python-profiles.py`，SHA `eadf29551ca2e706950d3f2311b47a3d08c2ccee3c8dd217fa299014a08e4286`。原 PythonVersion=3.10；三个库继承 pytest，python-slugify 原命令 `python test.py --verbose`。本次 CPU 为 Python 3.10.18，build stamp 20250918，`3.10.18 (main, Sep 18 2025, 19:50:32) [Clang 20.1.4 ]`，Astral python-build-standalone，由项目内固定 uv 0.8.22 安装。系统 Python、CAL2 环境和模型 SDK Python3.12 不变。

CPU 解释器位于 `runs/v051-hold-python310/cpython-3.10.18-linux-x86_64-gnu`，venv 位于 `runs/v051-hold-cpu-venv`。模板记录解释器二进制、BUILD、bootstrap、下载日志、wheel、全部普通文件 SHA、精确版本和编译信息。必要 engine 包固定为 pytest7.2.0、pytest-cov4.0.0、coverage7.6.12、attrs25.3.0、packaging25.0、pluggy1.6.0、exceptiongroup1.3.0、tomli2.2.1、typing_extensions4.15.0；venv 自带 pip23.0.1/setuptools65.5.0 如实保留。没有安装 funcy、slugify、iniconfig、dominate 任何目标源码。不是原 Docker image 的精确重现；这是旧 checkpoint 在明确记录的新 CPU 执行条件下评价。

`iniconfig` 是 pytest 宿主依赖与目标库同名的特殊接缝。新 worker 不加载正确 iniconfig 包，只提供无解析能力的配置 capability：接受冻结只读配置文件的绝对路径，验证当前字节 SHA 后返回预绑定 section/value；任意新路径、data 参数或其它参数均拒绝。pytest 内部持有这个受限对象，目标 canonical module 从候选工作树导入。候选进程中不存在可接受任意业务输入的正确 iniconfig module 对象或可读取的正确包副本。合成控制已证明同名候选的实际 `__file__`、正确包缺席、业务输入拒绝和外部文件读拒绝。

允许放行后作数据依赖准备：按原 profile 默认 `pip -e .` 的运行依赖含义，静态解析 setup.py 字面量/已知变量、setup.cfg install_requires、pyproject project.dependencies。**不执行目标 setup.py、不 build/install 目标、不生成正确目标源码。** 动态依赖、直接源码 URL、目标库依赖、不可解析声明或不支持配置直接阻断该固定库。第三方只接受 wheel，pip 按受保护 engine 精确版本约束解析，另存 additive dependency 目录；不替换 frozen engine，不允许目标包/.pth/startup hook。最终 wheel/依赖文件 SHA 与模板 ref 写入每库 environment，qualification 和模型 runner 使用同一对象，并在每次调用前核对冻结 engine 与依赖实际文件。没有为了提前凑环境而读取真实 setup/requirements。

## 真实执行与原生 ID

复用 r3 helper 的 Landlock/seccomp、子进程 session 注册、组清理和 60 秒墙钟/55 秒 CPU/4GiB 地址空间/8MiB 单文件约束；网络 syscall 仍禁用，不使用 boltons socket fixture。代码包和数据只从本次树及冻结 runtime/dependency 路径可读。结果绑定 helper/runner/environment、候选初始 SHA、逐文件 unchanged、原测试完整性、目标解析路径和实际装载路径。

pytest 保留原测试 union 和原配置；只有真实完整节点或充分归因至已改生产代码的 collection failure 才可判定代码结果。未观察节点明确保留，环境/宿主缺库、权限错误和无完整回执不填模型失败。原生 unittest 不转为 pytest：执行原脚本原 argv，用标准 TextTestResult 记录原生 ID 与实际 verbose description，再按锁定 profile 的正则逐行提取未经 strip/重写的 group(1)。只接受 ok/FAIL/ERROR；原始 union、description 和实际 native ID 必须一一映射，额外、遗漏、重复或 unsupported skip 不强行归一。若固定真实任务不满足这一契约，其资格阻断，不能读成绩后热修公共引擎。

## 24 个逻辑状态与唯一物理执行

每题 baseline/defect/reference 三个逻辑单元，八题总 24。导出后、任何测试结果产生前，固定完整 identity：全部候选文件 map、原测试 ID/引擎/配置、完整环境/依赖、runner/helper/profile、只读文件、生产基准及资源约束。只按该 identity 机械去重：baseline/reference 完整同值，或同库两题某态完整 identity 相同，则各逻辑单元引用同一次物理原件。失败/未知执行同样复用，不按成绩去重，不补跑失败。参考树用原补丁逆向构造，并与已冻 upstream 的全 map 字节严格相等，不读答案修改规则。

`plan.json` 在执行前保存 24 逻辑单元、唯一输入、来源和预定物理组数；准备已阻断的单元仍保留三个显式 not-executed 位置。`qualify` 最多四个 CPU 并发，unique input 一次。baseline/reference 要全部原节点通过；defect 要原 F2P fail/error 且 P2P 全通过，所有节点实际观察、来源/隔离完整。某题失败则该题四模型条件全部 blocked/Fnull，无换题、转预算或补试。合格子集可继续；`passed`（8/8）只是诊断，`completed` 表示八题资格盘点闭合。

摘要 version=`v051-holdout-source-qualification-v1`；字段包括 `source_root` 绝对路径、`adapter_manifest` 绝对 path/sha256/bytes ref、原顺序 `qualified_case_ids/blocked_case_ids`、`source_access_release/common_implementation_freeze/environment_template` refs、`repo_environments`、24 个 `logical_cells` 和各 physical_result ref。`physical_runner_invocation_count` 与实际执行分列；全部真实完成回执可得时 `physical_execution_count` 为完整值，否则 null，另列 known/unresolved。不能把 runner 调用或加载故障伪计成一次真实原测试执行。

## 合成控制与限制

`artifacts/software-calibration-v051/hold-source-controls/summary.json` 是最终可冻结摘要。5 个不同控制、6 次累计控制执行：首组 2 个真实 Python3.10 formal child，各 2 个虚构节点（每组 1 pass/1 有意 assertion failure）一次通过；纯 provider/去重控制各一次；随后为实际执行次数的未知计数修订仅重跑相关去重控制，并增加环境完整性/缺库归因的纯控制。真实 child 仍只有两次，未重跑原 CAL2/repo/SDK/tokenizer/TCP，也没有 HOLD 实际资格或模型调用。两个 child 的 worker、pytest/native instrumentation、配置 capability 与目标来源逻辑 AST 和最终相应函数同值；最终增加的执行前环境检查及 ImportError 归因由必要纯控制验证。

这些控制证明有限接口和隔离接缝，并不声明所有真实 HOLD repo 的依赖和测试已经合格。不符合冻结能力的题直接阻断。真实导出后不可按任务结果修改共同实现；发现实现完整性问题须保留原结果并向 root 报告，不能静默重试。

## 放行后的唯一命令（现在未执行）

从已封存 source 目录作为工作目录，显式设置冻结 src/scripts 路径，避免模块解析到主仓：

```bash
cd /data1/zhuxinrui/projects/ProWorkSim/runs/software-holdout-v051-common/source
PYTHONPATH="$PWD/src:$PWD" /data1/zhuxinrui/projects/ProWorkSim/.venv/bin/python -m scripts.software_holdout_sources_v051 export --project-root /data1/zhuxinrui/projects/ProWorkSim --source-root /data1/zhuxinrui/projects/ProWorkSim/artifacts/software-calibration-v051/holdout-sources --source-access-release /data1/zhuxinrui/projects/ProWorkSim/docs/experiments/software-holdout-v051-source-access-release.json
PYTHONPATH="$PWD/src:$PWD" /data1/zhuxinrui/projects/ProWorkSim/.venv/bin/python -m scripts.software_holdout_sources_v051 qualify --project-root /data1/zhuxinrui/projects/ProWorkSim --source-root /data1/zhuxinrui/projects/ProWorkSim/artifacts/software-calibration-v051/holdout-sources --source-access-release /data1/zhuxinrui/projects/ProWorkSim/docs/experiments/software-holdout-v051-source-access-release.json
```

随后由独立 `software_holdout_inputs_v051.py` 消费合格子集，按已锁 first_member 和各 checkpoint 身份构造初态；最终口径是 16 个角色逻辑形状、最多 64 个必要条件身份实例，来源不合格题不构造。具体执行命令由该脚本负责的 runtime agent 交付；没有追加模型资格。主 host 只接受来源/初态资格交集，并保留完整 32 行库存。
