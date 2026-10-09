# v0.39 零生成加载中止后的恢复启动

观察时间：**2026-10-09T15:44:11.816406+08:00**。用户明确要求实验验证与历史轨迹搜索并行推进。本次已于 **2026-10-09T15:41:23.118505+08:00** 启动持久恢复监督，PID **248758**；当前状态为 **waiting**，五个worker均未尝试，尚未开始模型验证。

## 原中止记录与恢复依据

原运行 `runs/software-organization-v039` 的接口诊断worker在加载权重时因 `shared_device_free_memory_reserve` 停止；它分配至GPU4的持续时间为 **29.630422592163086秒**。原报告、监督、退出栈及自动推送提交 `c9a76d14e3eca3a98a9d3c32c51be27e942c163f` 均保留，原运行目录没有改写。

本次没有只依据 `rows=[]` 判定零调用，而是检查了原运行全部10个文件：

- worker的 `task.json` 始终为 `load-original-common-actor`／`loading`；实际退出栈位于 `Qwen3_5ForCausalLM.from_pretrained` 的权重装载阶段。
- 没有resident owner、完整common恢复记录、episode目录、模型原请求／响应、SDK会话、experience或团队预算账本。
- 其余四个主实验worker的 `attempted` 全部为false。

这些控制流和原件共同支持：原尝试 **0个模型调用、0个模型输出token、0个episode决定**。因此本次接续只恢复未完成的加载和从未开始的冻结清单，不重复已经运行的诊断，不按结果重采。

## 新目录与不变边界

恢复目录为 `runs/software-organization-v039-recovery`。原 `plan.json` 逐字节复制，文件SHA256仍为 `110db40e62406ba441ca09ffb3a94f686f9daa22d23fe5beb1a382e1ede37b30`，内部计划摘要仍为 `4ce739d2be0bd6dbeed56fd55810ceb8dacc35684acbf5ed05967642b9de9e5e`。继续使用干净冻结执行源码 **`5159c13011d000e2949bc5e6b379463f63eeb9ef`**。

保留原先已通过的56项CPU资格，不重复执行；先运行两条各12决定／attempt、150000 token的独立接口诊断，再按原清单运行四root×F2／A3／X3×两seed共24条主实验。模型仍为原9B 3/3完整common；采样seed、先手、每episode预算、X3第8次团队决定后的单次事件及所有未知／失败保留规则均未改变。新增反向、actor与critic更新仍为0。

启动使用原 `finish` 入口，supervisor的 `CUDA_VISIBLE_DEVICES` 为空，worker仅可绑定物理 **3、4、5、7**；继承的副本GPU环境变量已移除。资源门槛仍为：启动前至少 **57344 MiB（56 GiB）**空闲并连续稳定60秒、进程自身不超过56 GiB、运行中至少保留 **6144 MiB（6 GiB）**。没有降低门槛、借用其他卡或停止无关进程。

## 当前容量与持久状态

原监督每5秒自行检查允许卡。该快照已保留 **29** 个连续采样，首末跨度 **162.7秒**；PID及启动身份一致，最新监督心跳为 **2026-10-09T15:44:06.871166+08:00**。

| 物理GPU | 空闲MiB | 启动要求MiB | 利用率 |
|---|---:|---:|---:|
| 3 | 17285 | 57344 | 98% |
| 4 | 17625 | 57344 | 98% |
| 5 | 17647 | 57344 | 98% |
| 7 | 25106 | 57344 | 69% |

当前允许卡均未达到启动门槛，因此恢复监督正在排队，并未把“队列运行”写成“已进行模型验证”。容量连续满足原门槛后，原监督会自动继续；诊断技术完整性故障仍会停止本批，诊断目标未达成不会自动重试或追加样本。

结束后，原finisher会按既有机制更新、提交并推送主[v039全库存报告](software-organization-v039.md)。主报告届时反映恢复目录；旧报告的完整副本另保存在 `runs/software-organization-v039-recovery/prior-publication/`。汇总全部实际成本时，应将原加载的 **29.630422592163086 GPU秒** 与恢复运行实际worker时间相加，不能丢弃原加载成本，也不能与episode时间重复相加。

原26次Contribution试训、3次正式更新、48条TextFSM确认及v037缓存生产验证继续暂停，不由本队列接续。

机器记录：[恢复启动与零生成核查](software-organization-v039-recovery-launch.json)。原件：`recovery-origin.json`、`old-zero-generation-review.json`、`launch.json`、`launch-observation.json`、`supervisor.json`，均在恢复目录；旧plan／监督／finish／worker报告及退出日志的路径与SHA见机器记录。
