# MATCH／PROJECT 双会话部署与最多六请求控制

本目录是待审阅的独立补丁与控制入口，没有应用到在途源码，没有停止服务、请求GPU或加载模型。REF保持现状。

## 现有resident不能安全热升级

现有 `ResidentOwner.dispatch` 只有 status/acquire/release/cancel_acquire/poison，episode端只有 begin/match_count/match_complete/project_complete/finish。没有重载manager、导出进程内模型对象、转交CUDA缓存或任意代码执行接口。修改磁盘文件不会替换已加载类；新外部manager也不能取得旧进程的model对象。禁止进程注入、ptrace及任意eval的前提下，不存在经现接口可执行的“零reload原位升级”。

原r3/r5 reservation不是外部设备租约：它在旧worker的PyTorch native allocator内保留可复用缓存，临时tensor已释放。`r5.use_startup_cache`要求相同PID，是同进程证据转接，不能把旧PID的缓存算成新PID已有显存。旧进程退出后缓存归驱动。项目flock仅防本项目重复分配GPU，不能阻止其他用户的CUDA分配。

因此不实施无保证的跨进程holder转移，也不把连续持有flock等同于连续持有显存。实际优先级是：如其他GPU按原46080MiB空闲门和固定UUID身份准入，直接在该卡加载一次新manager并做六请求控制，旧GPU6继续完成原任务；如没有合格卡，GPU6原任务自然结束、候选/账本/进程树均闭合后，做一次受控reload。源和依赖事先准备好，新服务立即走原r5 startup reservation再原loader，尽量缩短空窗；仍不能绝对保证其他用户不会在释放与重新分配间抢占。

若交接时空闲容量不足，保持resource_not_ready且不消费正式槽，不压缩上下文、不修改数值配置、不终止其他用户作业。真实load/control失败只记录一次，不自动重新采样或重复加载。当前是否有其他卡达门由根/provisioner当时的一次只读采样决定，不使用过期显存快照启动。

## launcher最小改动

`tools/run_match_resident_v054.py`新增固定spec-v3分支。spec-v2仍固定旧入口/单会话，不能通过增加字段悄悄升级。v3要求：

```json
{
  "version": "v054-match-resident-spec-v3",
  "session_protocol": "mp-interleave-v1",
  "maximum_sessions": 2,
  "owner_entrypoint": {"path": "<ROOT>/tools/serve_interleaved_owner_v054.py", "sha256": "...", "bytes": 0},
  "source_manifest": {"path": "...", "sha256": "...", "bytes": 0}
}
```

owner_entrypoint必须是精确reference且同值包含于sources；只允许该固定工具路径，拒绝任意脚本。sources还必须包含恰一份 `software_benchmark_interleaved_owner_v054.py`。其余UUID/lease、实际空闲显存再核、原checkpoint/contract、codec隔离、原r3/r5缓存和原load都不改。启动时仅将原owner CLI入口切为新serve，并加 `--max-sessions 2`；ready必须校验新manager实际identity的协议与容量。新serve只有导入新manager.main，不复制加载或推理算法。

## 六请求独立许可与控制

`tools/check_match_interleave_v054.py`提供唯一共享 `preparation_permit(*, resident_id, gpu_index, gpu_uuid, source_manifest)`，供provisioner和CLI使用。许可版本为 `v054-resident-interleave-control-v1`，总计最多6个真实生成请求，四个独立合成会话，不创建任何正式claim：

| 阶段 | 会话 | arm与seed | 请求 |
| --- | --- | --- | --- |
| baseline | synthetic-v054-interleave-baseline-a-r1 | MATCH，202610210561 | A1 agent，然后A2 condenser |
| baseline | synthetic-v054-interleave-baseline-b-r1 | PROJECT，202610210562 | B1 |
| interleaved | synthetic-v054-interleave-interleaved-a-r1 | MATCH，202610210561 | A1，跨过B1后A2 condenser |
| interleaved | synthetic-v054-interleave-interleaved-b-r1 | PROJECT，202610210562 | B1 |

两个interleaved会话在A1前都已acquire/begin；B1后先finish/release B，再让仍为同一window的A继续A2，从而覆盖一题关闭不能破坏另一题的RNG与会话。A2 tools为空，usage_id=condenser；A1保留原五种native工具schema身份，B1保留PROJECT原解码请求形状。只请求输出单词的短合成内容，不执行模型提出的工具。2048输出上限、原采样和模型数值路径不变；8192输入只约束本次合成请求体，不替代正式16384输入容量。

许可固定全部请求body、每会话请求序列、阶段顺序、每会话2/1次上限，总实际输入输出上限61440；绑定新resident ID、物理GPU index/UUID和封源manifest。既有串行两会话许可不兼容，不能用于此准入。

checker保存完整原请求、响应与native trace；三对A1/A2/B1分别精确比较raw文本、完整choices和usage、输入/输出token ID及逐token logprob、RNG before/after digest。不比较本来应不同的attempt ID、时间戳、window ID和工具调用传输ID；后者只规范化tool_calls[].id，完整工具函数与参数不变；独立window反而要求四个均不同。调用后检查共享parked RNG恢复、实际model object相同、六个生成turn FIFO有序且区间不重叠，保留每个turn真实证据。FIFO结果只针对观察到的六个turn；真实票据争用/取消边界由manager的必要CPU控制覆盖，不冒称这六请求是压力测试。

严格一轮：输出目录须不存在；任何未知响应、计费或隔离失败保留证据并拒绝准入，不发第七个请求、不自动重试。数值比较失败也保留已知实际费用，不归零。不重复完整上下文容量检查。

## 集成与实际执行由根统一完成

1. 合并newmanager、transport、session/pool门和本launcher/checker，冻结新source。provisioner从共享builder创建permit，并将同一ref传入spec及owner启动参数。
2. 先选择当前达门的新GPU；无可用卡再安排GPU6自然drain。新服务需独立unit、socket、output、declaration及append-only admission，原resident结果/引用保留。不能在旧unit内自动替换运行脚本。
3. 新resident一次真实load后，显式运行 `check_match_interleave_v054.py --declaration <new-declaration> --authorization <same-permit> --output <fresh-control-root>`。预期完成6calls/4sessions，实际结果未运行前保持pending。
4. pool仅在新receipt严格passed、同PID/model、全部输出/token/RNG一致、零未结清调用后注册MP2；失败不恢复正式派发。新会话仍按原计划槽、原预算、原时间门分配。

运行许可仅授权本次准备控制，不能据控制脚本自身宣称manager/部署已通过。本文写成时没有新load或生成结果。
