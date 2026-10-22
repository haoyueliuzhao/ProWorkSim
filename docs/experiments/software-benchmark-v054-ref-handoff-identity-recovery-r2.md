# GPU7 REF→MP 转接身份读取修复 r2

## 状态与边界

本项是六小时监控期间发现的运行故障修复，已实际完成。**2026-10-23 01:27:44（北京时间）原 GPU7 REF 安全退役；01:29:17 新 MP resident 通过既有六请求资格并注册；01:29:59 快照确认 GPU7 同时承接两个原 pending MATCH/PROJECT 槽，Qwen 总运行并发为 8。** 退休工具本身没有模型调用；后续 MP 准备发生 1 次加载、6 次真实资格请求及 1620 token，分开记账，不称为全程零模型。

只允许接续原 GPU7 REF 退休流程。原 Verified 500 REF 生成全部终态且实际占用静止是前提，CPU 评分可以继续，旧技术未知及其费用不改写。原 MATCH/PROJECT 在途任务、GPU3/5/6、其他用户进程、历史失败设备加载和科学配置均不改变。没有正式回合重放、训练或额外任务。

## 根因与历史

旧转接代码在 `software_benchmark_ref_handoff_pool_v054_r1.py:275` 直接读取 `ready['invocation_id']`；真实历史 REF `ready.json` 缺少该字段，也缺少后续使用的 `cgroup` 字段。只修第一个读取仍会在后面失败。

原 `admitted_resident` 本身允许这两个 ready 可选字段不存在，并已通过 GPU UUID、登记凭据、PID/start_ticks 和 systemd 状态校验，返回完整的 `observed['unit_state']`。正确身份来源应是其 InvocationID／ControlGroup 与原 ready.host_process 的组合，而不是修改历史 ready 文件。

旧 CPU fixture 人为提供了这两个 ready 字段，未覆盖实际历史格式。原 `convert_ref` 也有同样读取缺陷，因此这里不回退到旧转换函数。

原 retirement intent 创建于 **2026-10-23 01:01:43.358582（北京时间）**，SHA256 `6c48e3145340a75d980112855d2b93c1f0d43b4ecf4d9583f4cad2ffdacad04c`。后续 01:12 左右的监控发现时间不作为最初执行时间。异常在 `systemctl stop` 调用之前发生，原转换保留为 `failed_manual_action_required`，error 为 `KeyError('invocation_id')`，automatic_retry=false；不能直接清成 null 让旧流程重试。

## 独立一次性实现

新增 `tools/repair_ref_handoff_identity_v054_r2.py`，没有修改原 frozen source、ready、overlay、policy、Qwen host 或模型。

`freeze` 仅写新 `runs/software-benchmark-v054/ref-handoff-identity-recovery-r2/` 计划与 prior-failure。它绑定原失败转换、其内容 SHA、原 r1 intent、REF registration／declaration／ready、原 InvocationID／PID／start_ticks／cgroup／GPU UUID、所有既有 devices 摘要和源码。此阶段无 GPU probe、status API、服务或模型操作。

`execute` 要求操作侧先停止**仅 pool monitor**，并获取原 `provisioner.lock`。它重新读取原500 REF及全部1500 slot身份，调用原 `admitted_resident` 与 `collect_runtime_boundary`，重新取得完整生成终态、原worker/scope静止和resident idle/inflight=0的证据。正式队列、账本和评分结果只读。

具体身份门：

- 仅 `proworksim-v054-resident-ref-r2.service`、物理GPU7和原UUID。
- 从已经准入的 `unit_state` 读取非空32位InvocationID和受限cgroup路径；MainPID必须等于ready.host_process.pid。
- 历史ready不含可选字段是合法格式；如其已有invocation_id/cgroup，则必须与准入观察一致。
- 实际stop前再取fresh unit状态和`process_identity`，InvocationID、ControlGroup、PID、start_ticks必须完全一致。不同即拒绝，不停止服务。

通过后，独立目录先写新 retirement-intent 和 state-before-recovery，再将 pool conversion 写为显式 recovery intent，附原 failed 快照引用及SHA。原failed没有被抹去，也没有置null。

最多一次精确 stop；随后证实原unit终止、原PID/start_ticks不再存活、完整cgroup所有子组无进程，再构造**原 CLOSURE_VERSION** 的合法 closure，附 r2 plan、原失败、验证过的unit身份和真实stop回执。

使用原 `append_retirement`、原retirement_rule和原事件链追加退役。当前Qwen r6及原worker的r1 overlay reader可以直接校验，不需要热改或迁移在途host。完成时 conversion 转为 `ref_retired_waiting_for_mp_capacity`，继续挂 previous_failure/recovery_plan；全部既有devices和正式counter保持。

**此工具不加载MP模型、不发六个资格请求，也不 claim 正式回合。** 操作侧恢复原pool monitor后，才由原容量／UUID／lease门做GPU7的第1次MP加载和既有六请求双会话资格，再注册为可派发resident。旧GPU0/1/2/4失败不重试。

## 中断与重复执行

- 任意未完成验证输出留在独立 `validation-NNNN`；必要的显式接续重新取得只读边界，不覆盖旧证据。
- `stop-intent`在真实stop前持久化。若已有成功stop-receipt，接续复用它；若只有stop-intent而无成功回执，**拒绝再次stop，也不伪造returncode=0**，留待单独诊断。
- closure已存在时核验同plan及同stop回执，不再停服务。
- 若retirement event已追加而最终state写入中断，接续识别同registration／同closure的唯一既有事件，完成state收口；不会再次append。
- completed后只返回既有证据；既有devices或pool身份发生未知变化则拒绝。
- 没有自动重试模型加载或正式回合。容量不满足时仍按原monitor资源门等待。

## 必要验证

新增 `tools/check_ref_handoff_identity_v054_r2.py`，六项控制通过，定向 Ruff 通过：

1. **直接使用真实972字节历史ready和原intent unit_state**，确认两个字段确实不存在；采用准入unit身份成功且ready原件不变，已有可选字段冲突和fresh身份变化拒绝。
2. 只接受精确旧KeyError及其原intent，其他失败拒绝。
3. mock精确stop只发生一次，成功receipt复用；有意图无receipt时不重试。
4. fresh InvocationID变化在意图或信号前拒绝。
5. failed→recovery→retired保留原失败引用／SHA、devices及正式counter。
6. 调用原overlay事件校验器和reader验证带r2来源的原版本closure可接受；追加中断恢复不产生重复retire事件。

上述六项纯 CPU 控制中的真实service调用、进程信号、GPU probe、模型调用、模型加载、正式claim和实际pool state写入均为0。随后实际退休、MP加载／资格和正式派发另列如下；不能将控制的零调用用于描述整个实际部署。

## 已采用的操作侧部署步骤

1. 封存并记录原pool monitor的PID/InvocationID、argv/unit定义及state，只停止这个manager；不停止Qwen任务或REF模型。
2. 执行：

   `PYTHONPATH=src:tools .venv/bin/python -B tools/repair_ref_handoff_identity_v054_r2.py execute --plan runs/software-benchmark-v054/ref-handoff-identity-recovery-r2/plan.json --sha256 <sealed SHA>`

3. 依据新durable意图／stop回执／closure／retirement判断阶段。发生不明状态不重复stop，不清原conversion。若 completed成功，以原命令、原overlay恢复原pool monitor。
4. 观察GPU7首次MP startup／六请求资格／qualified_registered及原pending MATCH/PROJECT首次派发；不能把退休成功直接称为MP实验已提速。

详细queue快照和完整runtime-boundary只保留于runs，小计划／控制／回执可发布至 `artifacts/software-benchmark-v054/ref-handoff-identity-recovery-r2/`。不扫描或哈希权重、镜像、rootfs，不重新运行任务或评分。


## 实际执行结果

### 原 REF 退休

独立 r2 completed 时间为 **2026-10-23 01:27:44.634994**。新边界证明原500个REF生成均终态，原worker/scope静止且resident空闲，身份校验采用准入unit_state而没有改写旧ready。

精确 `systemctl --user stop proworksim-v054-resident-ref-r2.service` 返回 **0**。必须保留一个区别：服务自身停止后为 `ActiveState=failed`、`Result=exit-code`、`ExecMainStatus=1`，不是“服务正常返回0”。实际 `MainPID=0`、原PID/start_ticks已退出、cgroup全空，符合原退休合同允许的 inactive/failed/missing 资源闭合条件。该服务退出记录完整保留，没有通过清状态隐藏它，也没有据此改写已结束REF的代码成绩。

原注册 `events/00000001.json` 由新退役事件 `events/00000005.json` 合法退役，继续使用原 `v054-ref-resource-retirement-closure-r1` 和原retirement_rule。closure SHA256为 `1178cb8f1beb48ff76f37eb0b9dce7c1b2a22f89f8ff671f8083f3176d01638c`，退役事件SHA256为 `c5cfac770b17c4f5de80a48ab2eda8fcce760e44b1ee74901fe12c69071da49c`。

旧 `KeyError('invocation_id')` 转换留在 `prior-failure.json`，SHA256 `b5689a7c9074a4b078f79440764e68ca97871e926f47b4fcbe17e340fb24c113`，新conversion挂其引用与内容摘要。没有将conversion置null重跑r1，没有重试旧失败卡，没有改动其devices记录。

退休工具这一阶段：retired_resident_count=1、model_loads=0、model_calls=0、formal_claims=0、formal_episodes_replayed=0。其他用户进程停止数为0。

### 原 monitor 完成 GPU7 MP 部署

原pool monitor按相同定义建立runtime link并恢复，沿原policy在 **01:27:45.672347** 建立GPU7的 **attempt-1**，resident为 `mp-g7-0303dcc7`。未替换或重载其它正在运行的GPU模型。

原六请求双会话资格实际通过，记录：

| 指标 | 实际值 |
| --- | ---: |
| model_loads | 1 |
| actual_model_generation_requests | 6 |
| known_actual_tokens | 1620 |
| unsettled_requests | 0 |
| completed_sessions | 4 |
| maximum_sessions | 2 |
| formal_slots_claimed（资格阶段） | 0 |

同resident PID与模型、隔离会话、FIFO、三组输出／token trace／RNG转换相同的原资格条件均通过；会话间权重重载为false。该资格是部署一致性检查，不是新增 benchmark 题，不证明任务完成率提高。

**01:29:17.157249**，原monitor追加注册事件 `events/00000006.json`，SHA256 `0a17e47d94163e2385ec221340781742ea698d59b043c0c3cd4711f4f4eaf0c3`；状态为 qualified_registered，权重保持驻留。

### 首次正式承接

**01:29:59.718311** 的独立快照记录Qwen队列running，总运行8槽。GPU7的原MP resident已实际承接：

- `v054-PROJECT-pytest-dev__pytest-7236`
- `v054-MATCH-django__django-11433`

两者为原 pending 正式任务的首次执行，使用同一GPU7 registration；不是重跑REF或技术未知槽。初始承接只证明两会话真实派发，任务是否成功及完成速率仍由后续官方评分和小时监控报告，不据此宣布吞吐提升幅度。

## 可发布证据

`artifacts/software-benchmark-v054/ref-handoff-identity-recovery-r2/` 共补入25份实际小证据，合计150,195字节（不含既有CPU控制及索引自身）：plan、prior-failure、retirement/stop意图、stop回执、closure、retirement event、completed、owner identity、部署脚本/交接与重启回执、MP declaration/spec/ready/identity/admission/qualification/registration、首次正式派发快照及小型pool state前快照。

`evidence-index.json`记录各原始路径、大小及SHA；12,905,002字节完整queue快照与1,411,590字节runtime-boundary仅保留原路径引用，没有复制到artifact。没有重新执行模型、全量运行校验或payload哈希。所有r1原件、旧failed、正式队列与评分继续保留。
