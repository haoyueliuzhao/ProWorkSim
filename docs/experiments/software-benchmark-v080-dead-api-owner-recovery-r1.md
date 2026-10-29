# v080：API协调器OOM后的原对象恢复

本轮只处理原 `proworksim-v076-api.service` 的33对API环境及一个已消费的评分环境 `score-3536`。11:39:27的本项目journal明确记录该协调器被OOM killer终止；其16 GiB user unit同时容纳协调器与归档等子进程，不能把这一事件解释成API容器224 GiB父组耗尽。具体哪个分配触发OOM尚未取得堆栈证据。另一个Qwen协调器在11:38:41以JSONDecodeError结束，应独立修复。

恢复工具为 `tools/recover_api_owner_v080.py`，使用既有固定Python与Docker接口，不创建容器、卷、模型或评分回合，不改旧补丁、结果、评分、费用或源文件。只在验证原owner已退出、原claim／image／所有权标签与父组一致后，先停止controller、再停止actor，冻结原工作树。

每对环境流式保留controller输出和工作树，并验证压缩流的完整性，不把仓库全量解码到Python内存。已有完整可信controller-transfer凭据则复用；仅出现非空`.zst`不足以证明完整，因此保留旧文件并从已停止对象重新导出。默认大归档使用原256 GiB raw／16 GiB压缩界限；每个恢复进程限4 GiB地址空间，最多两个进程共享原四CPU片段。

完整导出后才删除确证归属的旧对象，并释放原执行预约。若导出异常，保留精确停止的controller／actor／volume作为唯一候选来源；必须确认PID为0、API父组下该容器cgroup已消失，才释放CPU／内存预约。此情形记录`technical_unknown`、`export_pending`和`retained_objects`，磁盘大小未知不会填0，末尾再处理。保留停止对象不授权重用其已消费任务身份。

原可信`result.json`保持不变；缺少原结果的回合先记技术未知，即使controller归档内部出现closed，也只作为后续离线校验的证据。评分环境只保留原日志、预测与停止后的工作树；已消费的评分身份不能被本工具重跑。5笔孤立费用预约的结算由独立恢复步骤处理，本工具不改账。

执行顺序（由主操作者执行）：

```bash
.venv/bin/python tools/run_offline_scorer_v058.py tools/recover_api_owner_v080.py --prepare
.venv/bin/python tools/run_offline_scorer_v058.py tools/recover_api_owner_v080.py --pair 3580
.venv/bin/python tools/run_offline_scorer_v058.py tools/recover_api_owner_v080.py --pair 3581
# 继续提案中的其余原索引；最多两个进程并行。
.venv/bin/python tools/run_offline_scorer_v058.py tools/recover_api_owner_v080.py --grader
.venv/bin/python tools/run_offline_scorer_v058.py tools/recover_api_owner_v080.py --summary
```

八项必要CPU控制通过，涵盖活owner／非名单拒绝、只读归档元数据、停止对象保留、活对象禁止释放、两worker上限、导出失败不删唯一来源、已完成恢复不重复执行。测试不操作真实Docker。运行证据保存在 `runs/software-benchmark-v080/dead-api-owner-r1/`，提案在 `artifacts/software-benchmark-v080/dead-owner-recovery-r1/proposal.json`。
