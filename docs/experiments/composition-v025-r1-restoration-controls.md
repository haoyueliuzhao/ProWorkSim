# v0.25 R1：同一失败更新前状态的整窗恢复控制

用户明确要求“重新进行实验”。R1 复用原16条支持窗口经历、原 terminal MC 和全单位 F0 组成，从原失败更新的 `shared-before.pt` 完整恢复后重新计算全部283个决定。它不重采支持，不从第267条继续，不复用已经丢失的部分梯度，不改变数值门、learner 或模型后端。

原 v0.25 在本窗266/283次反向后的资源查询失败停止，本窗 actor/critic 均未步进，后继确认与交互没有启动。原成本 **13.726392886042595 GPU小时** 保留，并与新的 R1 成本分别报告。新监督器与资源预算由 R1 运行方案负责；本模块不分配GPU、不启动工作进程或决定自动重试。

## 1. 绑定原件与无步进证明

新增 `src/proworksim/composition_recovery_v025.py` 提供：

```text
build_recovery_binding(old_run) -> plan_refs
restore_failed_window(owner, old_run, plan_refs, output)
    -> entries, composition, restoration_proof
```

`build_recovery_binding` 不加载 tensor。它固定原 supervisor、stage、guard、worker/update report、原entries/declaration/support/admission、原composition与逐行materialization、behavior checks、原计划及 `shared-before.pt` 的 SHA/大小，要求原监督和worker身份已终止。

准入只针对原 `v025-window-1` 的16槽、283个原决定与266条最后持久化反向计数，原表现为 `preparing/backward`、概率准入通过、本窗actor/critic步数为0。资源 guard 的首个记录触发为 `resource_query_failed`；旧 observer 恢复后记录的 `task_time_budget` 单独保留，不把它误写成新18小时额度耗尽。

冻结原 updater 在任一 optimizer.step 之前必须保存以下四个文件：

- `gradient-probability-check.json`
- `losses.json`
- `signal-diagnostics.json`
- `gradients-before-clip.pt`

四件均不存在，且没有base final checkpoint、base endpoint或完成marker，支持“没有进入任一参数step”的控制流判断。这不是读取进程临死时的tensor。原内存中的部分 `.grad` 没有持久化，不能宣称断点保存了266次反向的计算。

另比较旧 `e37432483e430d366ea706efc307caf86451d2e3` 中8个直接相关的 learner、composition、support、MemberView、信用/critic特征和函数式学习模块的原字节，确保恢复没有伴随更换算法或分母；不是重新开展全系统或大模型数值资格验证。

## 2. 实际原始状态的 CPU 读取

使用 `torch.load(..., map_location='cpu', weights_only=True)` 读取了原13MB小型 learner 状态，没有加载9B基座或执行模型forward。

| 字段 | 实际原件 |
|---|---|
| 文件 | `runs/domain-v025/train_base/actual/update/shared-before.pt` |
| 字节数 | 13,441,042 |
| 文件 SHA256 | `652e66b4da15913805c9a63f99680a58c3f886ee3e4a508ca75242fb05141507` |
| 完整 state tensor digest | `4d39266883472dd4ae550ef243b72cce24a65e4ee991cc5e0dcdf88c0062dcf7` |
| actor／critic／policy revision | 2／2／2 |
| 原 window | `v025-window-1` |
| 原 used IDs | `v024-window-1`、`v024-window-2-mc`、`v025-window-1` |
| actor optimizer state 项 | 32 |
| critic optimizer state 项 | 4 |
| CPU RNG | 5,056 bytes |
| CUDA RNG | 1个设备状态 |
| 已保存当前梯度字段 | 无 |
| 信用配方 | `terminal_mc` |

这份 snapshot 已包含原 `begin_window` 后的 window/used IDs，因此完整摘要不同于采样前 origin 的 `953ce...`。R1 必须恢复 `4d3926...` 这份失败更新前状态，不能把两种边界混为一谈。

## 3. 恢复流程与原件保护

恢复函数先重新核对 plan_refs 与原 run 的证据，读原entries与完整admission，重绑实际 rollout/member/Mapper，并核验原 `validate_composition` 结果与原逐行物化记录相同且所有权重为1。

随后在新 R1 输出下创建 `recovery-checkpoint/`，仅将原 `shared-before.pt` **逐字复制**为新的 `shared-state.pt`，并写明这是恢复包装、不是旧失败run产生的成功checkpoint。原失败目录没有写入、重命名或覆盖；输出路径若位于原失败目录内会被拒绝。

通过原 `owner.restore_checkpoint` 恢复 actor、critic、两个持久 optimizer、CPU/CUDA RNG、step/revision、原 window 与 used IDs；清除任何新 owner 上的残余梯度后，重新计算整个 `_state_bundle` 摘要，必须与原snapshot一致。

再次执行原 `prepare_window`，要求与旧 admission **全部字段和序列化 SHA 完全一致**；再次核对原composition及所有逐行权重。只有这些条件成立后，才将phase设为 `collecting`。不调用 `begin_window`，不追加重复window ID，也不改变episode/call身份。`restoration-proof.json` 在实际验证之后写入新输出，保存原件引用、完整state摘要、原步数、原ID、admission与权重一致证明，以及 `partial_gradients_reused=false`、`new_training_model_calls=0`。

实际新更新由原 `update_window(entries, composition=composition)` 从第一行重新开始；R1 运行器约束本次最多新增 actor/critic 各一步，即原2步至最多3步。此模块没有把原失败样本重新标注、替换为新数据或放宽支持门。

## 4. 两项必要 tiny CPU 控制

新测试文件为 `tests/test_composition_recovery_v025.py`。复用既有tiny fixture的准备代码，但没有重跑原组成梯度比较测试，也没有再次采集16个业务WorldCore episode。

第一项控制使用已有两次真实tiny CPU更新、含持久optimizer状态的学习器，以及8槽16个本人决定的明确CPU fixture。故意扰动新owner的actor/critic参数、两个optimizer学习率、RNG和 `.grad` 后：

- 从模拟失败前的完整原始state恢复，最终 `_state_bundle` 摘要完全相同。
- actor/critic/revision保持2，原window与used IDs不变；将 `begin_window` 置为禁止调用仍通过。
- 原admission全字段／字节SHA一致，原composition与逐行单位权重一致，全部残余梯度清空。
- 原输入文件字节全部保持，collecting owner不能再恢复，篡改原admission会被拒绝。

第二项控制限定无步进证据：必需步进前文件存在、原进程仍存活或原步数不再为0时，不能继续声称原窗口未更新。

结果：

```text
runs/v016-sdk/resident-venv/bin/python -m pytest -q tests/test_composition_recovery_v025.py
2 passed in 2.89s
```

相关恢复模块和测试的 Ruff 检查通过。另对真实原run执行只读 binding 构建通过，确认16槽/283决定与上述原成本；这不是新增真实学习结果。9B上的实际完整恢复与283行重算结果需读取后续 R1 原始运行记录，不能由本CPU控制提前宣称完成。
