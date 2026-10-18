# v051 HOLD独立测量与32槽宿主

新增`src/proworksim/software_holdout_measurement_v051.py`与`scripts/software_holdout_v051.py`。本轮只实现共同代码、读取原32条静态库存/checkpoint元数据并做合成CPU合同；没有读取HOLD业务源码或任务正文，没有执行实际HOLD来源资格、初态分词、模型资格、prepare、launch或GPU任务。CAL2报告与运行原件不修改。

最终purpose为`held_out_checkpoint_evaluation`，`holdout_evaluation=true`，training/contribution/independent_confirmation三项资格均false。HOLD是独立的只读保留状态评价，不恢复旧训练、独立确认或缓存生产队列。

## 原32库存、状态与预算

静态库存仍是funcy、python-slugify、iniconfig、dominate各两题，八题×`S_star/B/Q_plus/Q_minus`，共32行。原任务、来源行SHA、seed `202610170561—568`、每题四状态轮转顺序与先手001/002均按原metadata验证；每槽128决定、128attempt、500,000生成token、32次项目公开测试，完整上界16M token、4096决定/attempt、1024测试。每槽fresh resident，两个固定member_001/member_002、共享预算、O1原事件唤醒语义，无出生、替换或预算重置。

四状态必须精确绑定`inventory.states[condition]`。S_star历史4/4，其余5/5只是必要条件；B标签配Q_plus的合法5/5授权同样拒绝。测量还核对原checkpoint引用、source_actor_identity、retained_state_authorization、实际adapter身份及历史步数；宿主冻结时比对完整原状态表，不能置换标签。模型只装载actor，构造critic/optimizer和新增参数、反向更新均为0。

资源按当前授权GPU0—7、最多4驻留、原容量共享门；不存在闲卡60秒要求。保留原启动缓存、内存/RSS/磁盘、进程身份、900秒装载/资源阶段、600秒生成声明与900秒外层生成guard、90分钟soft与100分钟episode hard界、600秒测量/评分边界及独立child组清理。通过仅说明各自对应的约束，不冒称HF600秒是硬抢占。

## 固定提交F与两成员机械证明

HOLD唯一业务端点是最后合法固定提交的`F=R_joint`，含原测试与流程要求；不引入CAL2末树`R_code`或对未提交工作区补验。没有提交时，原assessment可为F=0且host final test=0；但该结果仍须通过完整来源、反馈、费用、身份、时间和只读guard。机械未决不能填0。实际行政删失保留joint口径，R_token/Q_token不冒称可知。

新measurement在私有namespace直接复用v050的两个固定成员投影、反馈、分页、生命周期和context/team/member-fixed拒绝证明代码对象。未使用CAL2 S1的两人改一人AST变换，旧模块globals与旧记录不改。新绑定替换source/interface/purpose/window、只读native actor与精确四状态授权；窗口为`holdout-v051:<slot_id>`。

初态协议明确没有强制初始测试或诊断。独立wrapper先验证新case声明，以及episode start/end原件中的`initial_diagnostics={}`、两个成员各空assignments和无initial_public_feedback，再只消除旧证明中的唯一“缺初始诊断合同”gap。原gap和精确缺席证据留在新回执；任何其他gap、权限/反馈问题或未决不被消除。

正式native绑定要求非fixture的真实直接推理owner与profile、原始generation IDs、实际transport记录，并使全部native prepared/started/complete与SDK回包的输入/输出/usage/actor多重集一致。所有实际请求必须闭合且费用与共享账本一致。不能仅凭返回条数、外观相同的fixture或F值放行。

固定端点额外绑定`final-candidate-lock.json`、raw/最终assessment、唯一评估次数和固定文件树。提交后的测试来源/执行未决仍未知；没有提交时不运行末树“救援”评分。`allow_cpu_fixture`只可用于明确CPU控制；正式host始终传false，且host终态判定要求`formal_model_admission_eligible=true`。

## 资格阻断保留完整面板

允许环境/input事前资格通过的原任务继续，但plan始终保存32行。任一任务来源资格或任一必要初态身份变体不合格，其四行初态为`source_or_input_blocked`、`attempts=[]`、正式F/Q为null；不换题、不把未用预算转给其余行、不把合格子集称完整八题面板。

宿主只派发`qualified_case_ids`，该名单必须是原顺序的来源合格与输入合格交集。环境blocked任务不必构造SDK输入，但摘要仍明确该状态。初态资格的形状/身份变体编码次数由独立资格协议记录；宿主不把总编码硬编码为16，只消费按任务闭合的资格结果。

通用资源监督器仅在私有副本作四个窄修改：worker模块字符串一次、32行初态构造一次、两个库存终止判定接受已处理的blocked状态。模型/world/measurement逻辑不以AST仿造成O1。库存`complete`表示合格槽已闭合、blocked槽已明确，不表示32个F均已知；有缺题则完整八题主效应保持null。全部任务blocked时记录32行阻断及0worker，不查询GPU。

## 源码冻结与独立model-admission

root先完成CAL2结案解释，再签发以下独立来源文件；这些不是本模块自动批准的步骤：

- `docs/experiments/software-holdout-v051-common-freeze.json`：`version=v051-holdout-common-implementation-freeze-v1`，`frozen_before_business_material=true`，绝对`source_root`、完整`source_files`相对路径→SHA及`source_commit`，并绑定必要控制、共同runtime/Γ1和CPU3.10环境。
- `docs/experiments/software-holdout-v051-source-access-release.json`：在共同冻结之后授权唯一HOLD来源/输入资格。
- 来源与初态资格摘要：均保留原八题状态及`qualified_case_ids`；来源摘要带`source_root`、`adapter_manifest`引用、common/source-access refs，输入摘要带common/source-qualification refs；正式摘要`fixture_only=false`。
- `docs/experiments/software-holdout-v051-model-admission.json`：资格闭合之后由root另行签发模型准入。

模型准入schema为：

```json
{
  "version": "v051-holdout-model-admission-v1",
  "released": true,
  "purpose": "held_out_checkpoint_evaluation",
  "unresolved_blockers": [],
  "common_implementation_freeze": {"path": "absolute", "sha256": "...", "bytes": 1},
  "source_access_release": {"path": "absolute", "sha256": "...", "bytes": 1},
  "source_qualification": {"path": "absolute", "sha256": "...", "bytes": 1},
  "initial_inputs": {"path": "absolute", "sha256": "...", "bytes": 1},
  "resource_policy": {"path": "absolute", "sha256": "...", "bytes": 1},
  "inventory": {"path": "absolute", "sha256": "...", "bytes": 1},
  "resources": {"allowed_gpu_indices": [0,1,2,3,4,5,6,7], "max_residents": 4, "idle_only_admission": false},
  "qualified_case_ids": [],
  "task_qualification": [],
  "checks": {
    "cal2_closure_explained": true,
    "common_implementation_frozen_before_HOLD_material": true,
    "fixed_inventory_bound": true,
    "source_qualification_closed": true,
    "initial_input_qualification_closed": true,
    "readonly_states_bound": true,
    "measurement_controls": true,
    "host_controls": true,
    "resource_policy_bound": true
  }
}
```

以上是schema示意，省略的八行必须由真实资格来源填写，示意值不能用于放行。`task_qualification`必须依原HOLD_IDS顺序包含八行，每行为`{task_id,source_status,input_status,dispatch_eligible,reason}`。source_status是qualified/source_blocked；input_status是qualified/input_blocked/not_run_source_blocked；dispatch_eligible精确等于两者共同合格，blocked必须有reason。资格未决题作为明确blocked记录，不放入qualified名单；`unresolved_blockers=[]`表示放行过程与允许的固定子集已确定，不代表八题全部合格。

prepare读取独立准入后才消费来源证据，必须提供显式project root。模型源码直接复制并比对common-freeze封存源码，不能重新快照打开HOLD业务后改过的main。source_root/adapter_manifest入plan前规范化为绝对路径并核对SHA；证据副本加序号，避免不同目录的同名summary被覆盖。旧CAL1/CAL2成本不加入HOLD模型账本；窗口费用需要时单独引用旧结案一次。

## 必要控制与原失败保留

新增五项纯CPU合同一次全部通过（0.15秒）：精确状态标签/授权；原两成员证明代码对象恒等与仅消除有证据的初诊断gap；native回包与实际usage多重集；F0不能绕过formal机械门且禁止末树端点；完整32行部分资格、路径类型和blocked监督状态。首次Ruff只有测试unused import，移除后通过。之后将缺原件与已证矛盾分开：缺证保持measurement_pending，已充分证明的完整性矛盾才为global_pause；只在原F0控制中补缺manifest反例并重跑该项，1 passed、4 deselected（0.13秒）。因此是5个不同控制、6项累计执行，未重复其余4项；最终scoped Ruff通过。只读接缝审阅发现并在首次控制前修复了`read_json`字符串路径问题，另修复不同来源同名summary副本的路径冲突。

另只读测量了runtime已保存的6响应/两真实SDK会话合成fixture一次，没有重建会话或重跑SDK。固定无submit F0、初诊断缺席、两成员生命周期等绑定成立，但综合结果为global_pause：其CPU证据标签不等于正式回放标签，且无真实学习/RNG guard hashes。原结果保存于`artifacts/software-calibration-v051/hold-measurement-controls/first-existing-fixture.json`，不宣称这是正式测量通过，也没有为它放宽formal门。它不替代HOLD来源/input资格或真实native证据。

本模块控制摘要：`artifacts/software-calibration-v051/hold-measurement-controls/summary.json`。正式HOLD业务、权重装载、模型、GPU、tokenizer、来源资格、prepare和launch在本子任务中均为0。

## 准入后命令，当前未执行

```bash
pws_project=/data1/zhuxinrui/projects/ProWorkSim
pws_common="$pws_project/runs/software-holdout-v051-common/source"
pws_hold="$pws_project/runs/software-holdout-v051"
PYTHONPATH="$pws_common/src:$pws_common" "$pws_project/.venv/bin/python" \
  -m scripts.software_holdout_v051 prepare \
  --project-root "$pws_project" --root "$pws_hold" \
  --admission "$pws_project/docs/experiments/software-holdout-v051-model-admission.json"
PYTHONPATH="$pws_hold/source/src:$pws_hold/source" "$pws_project/.venv/bin/python" \
  -m scripts.software_holdout_v051 supervise --root "$pws_hold"
```

资格未通过的槽不派发；已进入loader的模型槽不自动重排，只有充分绑定的pre-model资源不足可在新worker中重试。真实完整性问题暂停未开库存并闭合在途；安全局部context/预算终止在来源充分且F可评时继续独立槽，不按F高低筛选。32库存处理结束后无自动后继。
