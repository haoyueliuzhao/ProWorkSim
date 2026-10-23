# DeepSeek六组生成技术未知集中审计（r1）

本次只读核对原队列保留的161个generation technical_unknown，不启动模型，不重跑entered回合，不重新选择候选，不改原queue／claim／结果。原六组每组500题分母保持。

## 已取得事实

161项均有匹配原slot的result和completion，全部审计完毕、最终审计错误0。没有发现既有 `candidates`、claim侧 `candidate-result.json` 或官方code／delivery请求，因而**当前可直接离线重评分的可信锁定候选为0**。归档marker存在132项；本审计未解压任何归档或扫描rootfs。其余未归档现场不自动视为可信最终候选。

| 主要证据分类 | 槽数 |
| --- | ---: |
| PROJECT SDK尝试在一个opportunity内作第二次模型决策 | 54 |
| 原生tool arguments JSON解析失败 | 48 |
| 原生SDK工具调用与工具结果配对缺失 | 27 |
| 思考模式reasoning provenance／历史保存约束失败 | 10 |
| controller正常closed，但宿主缺完整绑定的quiescence | 8 |
| clone前manifest路径前缀被旧bootstrap拒绝 | 6 |
| 历史provider账单未定 | 2 |
| SDK改变原provider tool arguments | 2 |
| provider输出超请求上限、已结算且响应被隔离 | 1 |
| RPC停止无法证明静止 | 1 |
| worker失败后controller-result缺失 | 1 |
| native RPC BrokenPipe | 1 |
| 合计 | **161** |

分类采用最具体的既有证据；provider未定／明确上限事件优先于外层“controller failed”等通用错误。54项PROJECT分类依据managed-boundary所绑定sequence对应的 `interface_error`，不是仅凭外层execution_integrity_failure字样推断。为定位这些精确sequence，流式读取了约347 MB既有managed experience元数据；只导出匹配错误行的摘要、偏移和SHA，没有导出模型消息、工具正文或补丁，也没有遍历rootfs。

48项JSON解析失败中，最后一份已保留provider响应的finish_reason为length的有42项、tool_calls的有6项。这是返回形状证据，不能仅凭它断言所有任务代码错误，或认为扩大输出预算后必然成功。

共享账本共6条有failure_json的请求，其中本161项对应2条历史uncertain、1条r4超请求输出已settled；其余3条r4超请求输出属于原队列**非本161个生成未知槽**，在审计文件单列，不能把它们也算作本批未知原因。未改账本或释放未知费用保留。

## 六个astropy原槽的零模型边界

`astropy__astropy-12907` 的六组各有一个槽，均满足以下相互印证的小型历史证据：

- result记录entered=false，原claim state保持phase=claimed、entered=false、started=null；slot已经claim，旧claim仍明确禁止resume_or_resample。
- 共享SQLite按各自exact slot_id统计均为0请求；原r4 routing-result的actual_controller_routing_count均为0。
- 未产生entered.json、scope-registry、watchdog spec、resource slice、actor ready、controller ready／result及start.json；finally_stopped_scopes为空。
- 原job、claim、config与queue中slot／condition／arm／thinking／seed一致。四个REF／MATCH配置名为config.json，两个PROJECT配置名为budget-project-config-r4.json，均按原job argv实际路径核对，并与solver-routing保存的config SHA一致。
- stderr均指向 `native_uid_bootstrap_v055.checked_manifest` 的精确路径前缀拒绝：合格模板位于native-lazy-r3，旧helper只允许v055和native-lazy-cache。代码顺序表明该拒绝在manifest读取、destination copy之前，更早于actor／controller启动与enter_api。

因此六槽的**历史未进入API／模型边界有充分证据支持**，但这不是允许删除旧claim的依据，也不替代启用时的新进程静默、锁与资源准入。旧结果继续保留technical_unknown；若另行接续，必须是独立恢复namespace和原slot链接，不是原路径重试。其余155项本轮没有可直接恢复的锁定候选，保持原未知。

## 最小独立接续设计（尚未实施生成）

原ApiEpisode没有公开claim namespace参数；其claim根与episode输出限制均由 `software_benchmark_runner_v055.RUN_ROOT` 决定。可在独立恢复worker私有进程中仅绑定新的 `runs/software-benchmark-v055/pre-entry-recovery-r1`，复用原r4 controller routing、原六份配置、原共享2000元账本。保持原slot_id／科学配置／seed／模型／总预算；新claim侧增加original slot、旧claim、旧result和恢复plan引用，旧目录和unknown不变。共享账本原六slot请求数为0，因此原请求ID序列尚未消费，但启动前必须再次核对，而不是依据本次快照盲目执行。

路径修复应新增一个有限clone helper，只接受该**确切合格manifest SHA、prepared_root、device及初始化资格引用**，继续使用原numeric ownership映射与copy机制；不能将整个native-lazy-r3前缀无条件放开，不能热改原bootstrap。现有模板及资格可复用，不新建／下载模板或为资格重复复制大rootfs；正式回合原本要求的独立actor clone仍必须保留，避免六组共享可写工作区。

启用前应封存六个槽的恢复plan与新源码，持独立全局恢复锁，确认原精确worker退出、原claim未entered、共享API仍为0、旧原件hash未变、新namespace从未进入，保留原CPU／内存／磁盘预约与API并发门。任何证据变化即拒绝，不清claim、不变更旧状态。新生成和官方评分结果在独立恢复记录中关联原题，最终如何纳入修订后的完成状态须由明确的reconciliation视图说明，不静默覆盖原面板历史。本设计提交时没有运行模型或创建正式恢复claim；之后经技术审查开展的六槽首次实际执行另见[独立恢复记录](software-benchmark-v055-six-zero-model-preentry-recovery-r1.md)，不回写本只读审计的原161项统计或原0模型证据时点。

## 文件与审计范围

- [161项最终审计](../../artifacts/software-benchmark-v055/exception-reconciliation-r1/deepseek-generation-audit.json)
- [审计脚本](../../tools/audit_deepseek_generation_exceptions_v055_r1.py)

初次脚本错误地统一寻找config.json，两个PROJECT配置未被识别；初版159项和两项审计错误保留在 `deepseek-generation-audit-initial-partial.json`。修订按原job argv取配置后，复用已审计159项，仅读补两项，最终161／161且errors为空；没有为这次审计代码修正重读全部现场。Ruff通过。读证据、写独立审计文件之外，模型／API／GPU／systemd调用、任务重放、候选重选、队列与claim修改均为0。
