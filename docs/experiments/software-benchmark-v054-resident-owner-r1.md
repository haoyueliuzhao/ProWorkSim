# v054 MATCH／PROJECT 常驻 owner 修订

本修订只改变服务驻留与会话生命周期。原始 Qwen3.5-9B 在 GPU6 上通过原 `load_actor` 加载一次；MATCH 和 PROJECT 都保持原 project 数值路径、BF16 backbone／FP32 head、18,432／2,048 合同、原采样以及 r3/r5 allocator 协议。没有训练、适配器、数值方法替换、`empty_cache` 或逐槽重新加载权重。

## 独立会话

`ResidentOwner` 每次 acquire 创建新的 `FormalOwnerService`、调用日志目录和 Unix socket／identity；MATCH 的 `MatchBridge` 和其 ledger 也重新创建。PROJECT 的 S1预算、SDK/history和工作区仍由共同runner每槽重新构造，不能复用上一槽controller。owner日志目录只改变记录目的地，不改变模型。

原 `capture_evaluation_state → begin_window → reseed` 与 `finish_evaluation → finish_evaluation_guard` 原样执行。finish恢复Torch CPU／CUDA RNG并验证原只读学习状态；随后release确认无在途请求、owner idle、GPU工作同步、原生成器的临时 `model._cache` 已消失，才接收下一槽。保留的是模型和可复用CUDA allocator缓存，旧prompt／生成历史／KV不进入下一槽。`used_window_ids` 和已用槽身份仅作禁止重放的控制记录。

正常窗口使用独立epoch和claim身份。旧socket被关闭、删除；旧claim不能作用于新session。原数值方法 `CalibrationActor.generate_native` 的函数身份始终检查，模型对象和raw identity保持不变。无需为服务驻留重新运行已经完成的正式题或原容量上限验证。

## 共同runner接口

GPU常驻进程属于独立unit，持续持有物理UUID和全局resident lease。episode的model role应为CPU session sentinel，不能把常驻unit纳入每题stop列表。

管理IPC沿用 `OwnerClient` 的完整帧和身份协议：

- `acquire(slot, claim_id, authorization, host_process)`：在正式claim之前租约；忙返回 `acquired=false,state=busy`，不begin、不seed、不生成。成功返回 `session_socket/session_identity/session_root`。
- 会话socket使用原 `begin/match_count/match_complete/project_complete/finish`；`begin`必须和预租的slot／claim／授权完全一致。
- `release(claim_id, finish_receipt)`：`finish_receipt` 是原finish返回的 `receipt` 引用，不是整个返回dict。成功返回 `quiescence` 和持久化回执。
- `cancel_acquire(claim_id)`：仅从未begin的租约可取消。
- `poison(claim_id, reason)`：立即封死后续调用与复用，不等待正在生成的锁，不卸载模型或释放GPU lease。

未知账单／协议故障永久poison。外部sentinel按严格unit／InvocationID对整个resident cgroup执行SIGSTOP，可保留显存；没有自动CONT或复用。SIGSTOP不等于已提交GPU kernel立刻被取消，未知费用继续保留。仅显式停服才清理所有子孙并释放lease。

## 启动规格

入口为 `tools/run_match_resident_v054.py --spec FILE --sha256 SHA`，运行在 `proworksim-v054-resident-mp-rN.service`，`KillMode=control-group`、`Restart=no`。spec version为 `v054-match-resident-spec-v1`，包含 `unit/card/root/short/capacity_receipt/contract/load_admission/sources/identity_path/ready_path`；可选 `preparation_permit` 必须是独立合成许可。

launcher读取已有真实MATCH容量资格和原模型stat回执，持有 `GpuLease`，启动长期CPU官方codec及原loader一次。ready包含 `ready/resident/source_spec/host_process/gpu_index/gpu_uuid/gpu_lease_held/identity/admin/unit/invocation_id/cgroup`。管理socket为 `short/admin.sock`。新`launcher-started.json`禁止同一输出目录自动重启。

## 必要验证与边界

CPU小控制 `/tmp/v054-mp-owner-control-r3/receipt.json` 使用明确的程序化owner和字符tokenizer：验证连续MATCH→PROJECT的同一owner、新seed/window、MATCH ledger清零、PROJECT不继承MATCH账本或上一prompt、独立调用目录、fixture RNG恢复、旧socket/claim隔离，以及未结故障poison后拒绝复用。它没有加载模型或真实tokenizer，不宣称验证真实CUDA RNG／内存。

真实交接控制由 `tools/check_match_resident_handoff_v054.py` 准备并执行。先用 `--make-authorization FILE` 写 `v054-resident-session-smoke-v1`，然后把该引用绑定到启动spec的`preparation_permit`；再用 `--declaration FILE --authorization FILE --output NEWDIR`。许可仅两个固定synthetic session：先MATCH、后PROJECT、不同seed，每个最多一次原合同生成，总计最多两次，不领取正式槽、不给真实题内容。旧owner通用execution gate收到的内部许可仅含当前synthetic ID，且明确 `formal_execution_authorized=false`。

实际控制还核对相同resident PID／模型对象身份、完整真实token usage、原finish/RNG guard、原临时模型cache已清除、allocator仍驻留及各自独立的r3/r5资源日志。运行失败保留完整回包和未知费用，不重采。本补丁交付时尚未由本代理执行真实GPU交接，实际结果由根协调器单独记录。
