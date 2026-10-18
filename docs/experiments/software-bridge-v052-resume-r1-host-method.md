# v052 resume-r1：仅原三条未进入槽的独立宿主

实现为`scripts/software_bridge_v052_resume.py`，版本`software-openhands-bridge-resume-r1-v0.52`。用户已明确要求“恢复任务，此外排查异常信号”；root另行签发精确来源绑定的release。本模块只准备续接能力，不自行prepare、launch或恢复模型。原`runs/software-bridge-v052`、7d95912源码、首阶段报告、暂停及四个中断未知保持不动。

## 原库存与预算

只接原列表中的三行，顺序、seed、先手及每行全部字段从原plan复制：

1. `v052-cal2-xmltodict-1-PS1`；
2. `v052-cal2-xmltodict-2-PS1`；
3. `v052-cal2-xmltodict-2-OH_ref`。

原host必须终态paused且有ended_at，全部attempt已结束；状态恰为5 complete、4 stopped、3 not_started。三条not_started必须attempts为空，原slots及workers目录均不存在。其余九条还要绑定原started.json与原plan/attempt。原四个中断槽即使被改标为not_started也不能获得准入；没有精确恢复包不等于允许重新生成。

新root固定`runs/software-bridge-v052-resume-r1`，已有目录即拒绝。新上限3槽、1,500,000生成token、384决定、384attempt、64次PS1公开测试；每槽仍500,000/128/128，PS1每槽32测试。原未用预算转移为0。GPU0—7、容量共享、最大驻留4保持，库存只有3故最多实际派发3个；没有新增样本、seed、资格请求或学习更新。

## 原代码对象与私有命名空间

原v052 `worker`的code object完全不改，通过FunctionType放入私有globals，只绑定新frozen及独立host版本/模块；原CONTRACT/LIMITS为同值副本。原通用supervisor的AST只替换一个worker模块字面量为`scripts.software_bridge_v052_resume`，资源、进程、deadline、清理和暂停循环保持。worker_completion仍是原code object，在私有namespace中调用原v052 classify_closed。原模块globals不被monkeypatch。

正式结果未知、guard/账单未决或执行异常仍stopped并暂停新库存；充分绑定的安全context/预算终止且代码0仍可complete。没有按成绩筛选。仅原来有凭据的零模型startup容量失败允许在本新root按原规则重新分配；任何loader/模型已进入槽不重采。

账本调用原v052 ledger code和原native_accounting，只薄改库存标签：`logical_inventory=3`、`new_inventory=3`、`original_unique_inventory=12`。旧成本不加进新账本，初始未闭合端点仍null，不把无report当0。首阶段JSON仅为未来唯一合并的一次成本来源。

## 源码与资格复用

原plan实际source_files为616条；代码不硬编码这个数量，而是逐路径/字节SHA精确保留整张原map。从原run/source复制原件，绝不从后来main重新快照模型代码。`source_commit`继续7d95912b4ce9ae3130b01b4ce87bc26f9e2e5b9d；新增宿主独立记录`resume_host_commit`与`resume_host_source_files`，不能覆盖任何原路径。新snapshot只含原Python文件集合加该宿主，出现额外或缺失文件均拒绝。

frozen复用原bridge.gate_records核旧完整12行及原source/input/model admission，之后严格派生原3。原模型、tokenizer数值合同、测试runtime、OH reference-runtime、资源模块、角色和资格refs完全同值。没有重新编码、SDK捕获、三态资格或模型资格。

每次启动还绑定原plan/supervisor/pause/首阶段报告SHA。首阶段报告虽保留原`final`文件名，其角色在新plan是predecessor_stage_report；不移动、不覆盖，不当作整轮新结案。新模型源和源树与新宿主提交分别声明，避免把新增调度入口伪称原提交文件。

## 独立release合同

默认路径为`docs/experiments/software-bridge-v052-resume-r1-release.json`。必要字段：

- `version=v052-bridge-resume-r1-release-v1`、`stage=v052-OH-BRIDGE-resume-r1`；released与user_resume_authorized均true，unresolved_blockers为空。
- 四个绝对ref：predecessor_plan、predecessor_supervisor、predecessor_pause、predecessor_stage_report。
- protocol、controls、resume_host_source refs；controls版本`v052-resume-r1-host-controls-v1`、passed=true，并以相对key `scripts/software_bridge_v052_resume.py`绑定同一宿主ref。
- supporting_references至少有signal_observation_control、interruption_audit、partial_accounting_audit，允许其它只读refs。
- selected_slot_ids精确上述原三行；original_interrupted_remain_unknown=true、exact_resume_state_available_for_interrupted=false、old_remaining_budget_transfer=0。
- resources精确为allowed_gpu_indices=[0,1,2,3,4,5,6,7]、max_residents=4、idle_only_admission=false。
- signal_observation包含scope=supervisor_only、follow_forks=false、worker_wrapped=false、restart=no。实际systemd/strace安排由root负责，不在本模块实现；不要求SIGTERM来源已经查明，也不从未知来源推断归因。

checks精确八项均true：predecessor_terminal_no_inflight、only_three_never_entered、all_nine_entered_excluded、four_interrupted_unknown_preserved、original_scientific_sources_unchanged、original_qualifications_reused、resume_host_controls、old_budget_and_costs_not_transferred。

prepare要求git clean；写入前核对上述refs、原停机/源map、九条entered记录和三条目录缺席。新run保存编号evidence副本避免同名覆盖。签发release和运行prepare均不由控制测试代替。

## 有限新控制与命令

`tests/test_software_bridge_resume_v052.py`仅三项纯控制：原三库存及中断改标/已有目录反例；原worker/ledger/completion code对象及私有namespace/单literal；明确授权、旧科学合同/预算不转、初始null、未知暂停与充分绑定代码0继续。首次3 passed（0.10秒），scoped Ruff一次通过。没有重跑原host4项、旧SDK、模型、tokenizer或来源资格。

摘要为`artifacts/software-bridge-v052/resume-r1-host-controls/summary.json`，SHA `e0ce5279c8940041c1017a7d16f15a25e1c173d006592106bf3c334b18ae0c3e`。控制只证明新metadata/namespace接缝，不冒称真实续接已运行。

准入并提交后由root执行，当前未执行：

```bash
PYTHONPATH=src:. .venv/bin/python -m scripts.software_bridge_v052_resume prepare \
  --project-root /data1/zhuxinrui/projects/ProWorkSim \
  --root runs/software-bridge-v052-resume-r1 \
  --release docs/experiments/software-bridge-v052-resume-r1-release.json
```

supervise由root从新source执行并加外层supervisor-only信号观察；worker仍由原资源循环启动，未被strace包装。本模块拒绝对已有supervisor自动重启或重复prepare。三槽结束后另由独立报告器把原9与新3唯一合并；旧四未知、原调用预约和已计成本仍保留，无自动后继。
