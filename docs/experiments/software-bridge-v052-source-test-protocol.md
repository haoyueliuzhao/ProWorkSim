# v052 六题桥接：共同来源、实际测试入口与关闭候选

本层只服务新 v052 的原 CAL2 六题：boltons、parse、xmltodict 各两题。它不修理 funcy/slugify，不补验旧 HOLD 的未提交工作区，不回写 v051 评分或来源回执。当前已完成只读身份映射、独立薄适配、两项必要纯 CPU 控制及事前资格计划；**正式三态执行尚未放行，OH 原生终端的真实接缝控制由独立 adapter agent 完成后另行绑定**。本文件不授权模型。

## 1. 可复用的旧身份与不能代替的新资格

| 对象 | 已有冻结身份 | 本轮用途与限制 |
| --- | --- | --- |
| 六题原缺陷文件、问题、原完整测试 union/config | `cal2/adapter-manifest.json` SHA `5d5504ea21ccfe18cf67676614febe8fb6890693ad054c542237c30b44dcf5eb` | 直接复用原字节、任务 ID、source row SHA、许可与来源，不更换题目 |
| 正确/缺陷/参考三态旧 qualification-v2 | 摘要 SHA `fad44d31c9668d0a5b871c0470a7481bc3dbd155eb84763f594bdf3eddf59c2f` | 原来源行为与 map 证据可复用；执行是未隔离 `python -m pytest`、外置 recorder、180 秒，不能当作最终 r3 child 路径的完整资格 |
| 最终 r3 测试 child | `runs/software-calibration-v051-cal2-r3/source/src/proworksim/software_calibration_repo_tests_v051.py` SHA `68337e5ceb8ad4fffc691c4fcfd71937e6af8c886a2d80a24074d1abacb1644e` | 直接动态载入同一冻结文件，实际 subprocess 仍执行该文件；不复制或改写 executor |
| 最终 r3 隔离 helper | 同目录 `software_calibration_shell_v051.py` SHA `10ca8ef7a301be723f4acda390020fe87f3e8b0886ea9de619ac9366aea14f48` | 原 stdlib-only 动态入口、Landlock/seccomp、子组登记/清理直接复用 |
| socket 修复控制 | `socket-type-repair-r3/summary-r3.json` SHA `24c1ba9bceaeabbd803690f8998f5a61d86cf645e842911c26ba870eaa44c62a` | 原 async + 两 TCP 节点一个真实 child 3/3 已通过；原类身份保留，不重复这项控制。它不是全六题三态资格 |
| r3 已完成模型候选结果 | r3 plan 为提交 `505e83956f3d91bd4547e5f00d845cfffae0775e` | 保留原结果，不重新评分；模型候选/3-node 控制不能作为完整原始三态身份直接复用 |

因此本次复用的是旧来源、环境、最终执行器和有限控制；**现成完整且同最终身份的三态物理执行复用数为 0**。不把旧“来源曾通过”简写成新正式路径已经合格。

共同 CPU invocation 保持 `/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-calibration-v051/cal2-sources/cal2/cpu-venv/bin/python`，实际链接 `/usr/bin/python3.12`，原环境声明 Python3.12.3。依赖为 attrs26.1.0、coverage7.6.12、iniconfig2.3.1、packaging26.3、pluggy1.7.0、pytest7.2.0、pytest-cov4.0.0。本轮不迁移到 HOLD 的 Python3.10 环境，也不静默升级依赖。

新 runtime manifest 绑定解释器二进制、venv 与 Python3.12 stdlib 普通文件及符号链接目标、必要系统库、原环境 metadata、精确 runner/helper。每次真实调用在进入 child 前验证这些绑定；候选可读路径内的 venv 不含 boltons、parse 或 xmltodict 正确包。最终 r3 child 是新启动的隔离解释器，pytest 导入后把本次 worktree/root 与 src 前置，参考源码目录不在 Landlock allowlist。

这是明确的 cold-child、sys.path 与允许读取路径的来源证明，**不伪造旧 runner 未记录的目标 `__file__` 观测字段**。本次三个目标均不是 pytest 宿主依赖；HOLD iniconfig 的同名 config shim 不被牵入。测试 child 只加载同目录 stdlib helper，不导入 proworksim 包或其 openpyxl 等宿主依赖。

## 2. 两路真实测试入口

新 `src/proworksim/software_bridge_sources_v052.py` 是 host 层薄适配，正式函数为：

```python
run_repository_tests(*, files, task, run_root)
RepositorySources(source_root, *, runtime_manifest,
                  expected_manifest_sha256=None, runner=None)
run_native_public_tests(*, provider, task_id, candidate_files, run_root)
```

provider 沿用原 CAL2 `build_case/validate_files/runner_spec/run_public_tests/assess_files`，保留原 P/raw 模型可见版本、purpose 和 Γ；新 runtime/ref 字段只用于宿主绑定。PS1 公共测试直接使用该 provider；OH-ref 保留官方 TerminalAction/Observation 与 Agent/Conversation 原生循环，通过官方 TerminalTool 的 executor 注入能力，披露一个无参数 `bridge_run_tests` 命令。该命令的真实 terminal handler 调用 `run_native_public_tests`，再进入同一 `run_repository_tests` 与同一个 r3 child。

OH 普通 shell 仍按其声明工具执行并保留命令、测试机会和成本；不把任意字符串形式的 `python`/`pytest` 命令冒称已经走了共同权威入口，也不靠不完备字符串识别声称所有 shell 测试都等价。PS1 的原 32 次公开测试池与 OH 原生终端机会不是一一对应，比较是两个明确运行配置的组合影响。

OH 正式测试命令和最终代码验收都恢复原 tests/config/support 及原不存在的配置状态，保留合法生产修改、新增 helper 和真实删除。PS1 public interface 仍遵原 readonly/文件集合权限；原生 OH 的任意编辑不会改变最终权威测试集合。原始 candidate 和恢复后的 grading tree 分开保存。测试中没有开放任意外网；原 boltons 两个 loopback 测试使用 host 预置的有限真实 FD，真实 socket 类本身及可继承性保持，asyncio/ssl 语义按原 r3 有限控制复用。

## 3. 关闭前唯一锁定，固定交付与代码端点分列

关闭时先调用：

```python
lock_ref = lock_final_candidate(
    provider=provider, task_id=task_id, candidate_files=files, run_root=lock_dir)
# PS1 在锁定后执行原固定提交验收；OH 的 R_joint 为 N/A。
terminal = grade_locked_candidate(
    provider=provider, lock_reference=lock_ref, fixed_assessment=fixed_result_or_none)
```

lock_dir 只能新建一次，保存完整 raw candidate、恢复后的 canonical grading tree、原 readonly 恢复/新增排除/合法生产增删清单、task spec 与完整执行 identity。provider 已有权威评分记录时拒绝新锁，防止先看固定提交分数再选择末树。root 的 PS1 私有 collector/world 只改这处关闭评分接缝：先锁当前 member_001 bundle，再按原固定提交合同计算 R_joint，最后读取已锁对象计算 R_code。OH 同样在原生 episode 关闭后唯一锁树，R_joint 明确 N/A。

`assess_files` 顶层补充 `evaluation_identity`、`authoritative_runner_receipt` 和 `bridge_binding`。只有 PS1 有固定提交且 canonical tree、完整 task/runtime identity 严格同值，才核对两份原件 SHA 后复用一次权威执行。不同树单独执行并保存其结果与成本；公共 `run_tests` 不是关闭时固定提交权威缓存，不能据它选择候选。复用不依赖成绩，通过、失败和未知同等处理。

`grade_locked_candidate` 返回 R_code/Q_task、observed 节点、`new_evaluation_attempts/new_test_executions`、固定提交存在/复用标记及原 assessment。相同树复用时新增执行数为 0；新真实执行次数依 `command_executed`，不是把一次 wrapper 调用都算成业务测试。assessment/entered 文件阻止第二次评分。文件锁、runtime 或来源不匹配拒绝继续；基础设施缺证保留未知，不评分多候选择优。

生产 canonical 规则直接复用原明确范围：boltons 包内合法 Python 文件；parse/xmltodict 顶层 helper.py；原生产文件的删除保持。新增 conftest/pytest.ini/.pytest.ini/pyproject.toml/setup.cfg/setup.py/tox.ini/startup 等不能进入权威树。所有原只读测试、配置与 support 恢复。仅用于本轮新槽，不访问旧 HOLD 工作区。

## 4. 事前 18 逻辑 / 9 物理资格计划

只读 prepare 已创建 `artifacts/software-bridge-v052/source-qualification`：

- `runtime.json` SHA `7ee743488e79b2ddc6d8c1a6bfe461f11b8b92f72be4bb49b4e657a41b6c0d4f`，248663 bytes。
- `plan.json` SHA `1fc1077e03c2d6ddb3e9dc50174539d85f0cad597e0428c3d23ddd8f6b3412c1`，253253 bytes。

prepare 没有运行 pytest、SDK、tokenizer、模型或 GPU，只读取并绑定现成源码/环境/状态 map。六题每题 baseline/defect/reference，恰好 18 个逻辑单元；完整身份去重后为 **9 个物理执行**：每库一个共同 baseline/reference，加两题各自 defect。每个逻辑单元都保留指向自身 source row 和共享 physical input 的绑定；不按结果去重，不重复失败。原测试 union 分别为 boltons412、parse98、xmltodict60，不删除节点。

脚本 `scripts/software_bridge_sources_v052.py qualify` 在入口强制检查 root 独立 release：

```json
{
  "version": "v052-shared-source-execution-release-v1",
  "released": true,
  "plan": {"path": "absolute plan.json", "sha256": "...", "bytes": 253253},
  "logical_unit_bound": 18,
  "physical_unit_bound": 9,
  "same_terminal_entry_control_passed": true,
  "terminal_entry_control_refs": [{"path": "absolute receipt", "sha256": "...", "bytes": 1}]
}
```

此段是 schema，不能作为实际放行记录。必须先完成真实 OH TerminalTool 路由至共同 executor 的有限 CPU 接缝控制，并由 root 冻结控制引用、源码和上限。之后最多四 CPU 并发执行唯一九个身份，baseline/reference 要完整原测试全过，defect 要原 F2P fail/error、P2P 全过，且实际全部节点、完整性与隔离绑定合格。已进入的 physical 目录拒绝重入。失败保留原件、阻断相关资格；不自动修依赖、换题或重试。

待 root 放行后才可执行：

```bash
PYTHONPATH=src:. .venv/bin/python -m scripts.software_bridge_sources_v052 qualify --output-root /data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/source-qualification --release /absolute/root-issued-release.json
```

机器摘要 version=`v052-shared-source-qualification-v1`，保留六题 qualified/blocked、18 logical cells、真实 physical runner/command counts、runtime/plan/release refs。模型准入由 root 在来源、两路真实入口及其它必要门闭合后另行决定；本脚本不启动 12 个模型槽。

## 5. 本轮必要控制与当前待门

本层新增两个纯 CPU 控制：唯一预锁/原件保留/生产删除和 helper 新增/readonly恢复/禁止后选；同完整 identity 的固定回执复用/不同树独立一次/改锁拒绝。首轮 1 pass、1 fail：fake bridge-binding 把正式键 `execution_identity` 错写为 `evaluation_identity`，真实实现正确拒绝该缺键回执。原日志与首次源码保留；只修 fixture 并重跑受影响一项，最终 2 个不同控制、3 次累计节点执行通过，正式实现没有为通过 fixture 放宽绑定。scoped Ruff 通过。

首次源码复制时 module 与 script 同 basename 触发 cp 不覆盖提示；module 原件已保存，script 在源码未变化时按独立 scripts/ 子目录补存。没有因此重跑任何控制。该记录与首失败都进入独立 summary，不改成“首轮全过”。

这些纯控制没有执行任何真实仓库测试，也不能替代 OH 真实终端控制或九个正式三态执行。原 r3 socket/隔离控制精确复用，不再次机械重放。现阶段仍待 OH 接缝回执、root source execution release、唯一三态实际结果和后续模型准入；新增模型/SDK/tokenizer/来源测试数均为 0。
