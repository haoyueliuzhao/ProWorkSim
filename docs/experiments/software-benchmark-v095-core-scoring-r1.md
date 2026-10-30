# v095：已有候选的独立官方补评

本批落实用户本次“处理这些问题”，只补评固定的45份已有候选：43份v094正常闭合候选、6068经独立审计恢复的唯一终稿，以及原评分进程中断但已确认旧容器不存在的3536。模型调用为0，原补丁、原结果和失败记录保留。79项新生成、额外恢复候选及历史环境修订不属于本批授权。

## 根因与修复

43份旧评分的manifest逐字段比较只发现一处差异：API管理进程加载tokenizer时把 `deepseek-recipe==0.2.0` 所在overlay加入 `sys.path`，随后在该进程生成的评分manifest包含此额外依赖；独立评分子进程没有该overlay，严格校验因此失败。现有证据不是 `__main__` 改变模型或评分器源码。

新manifest直接由与真实评分相同的固定Python、独立 `python -m proworksim.software_benchmark_rescore_v095 --manifest` 子进程生成。原完整manifest校验保留，没有忽略依赖差异。原官方环境、测试、补丁应用和评分规则保持；新资源身份与run ID避免读取旧评分缓存。

6068只允许独立审计列明的 `recovered-result.json` 和 `terminal_code-lock.json` 两个精确引用，不能把任意未知状态或其他目录当作候选。其原生成异常不改写，项目正式交付仍为否。3536依据精确旧ID的NotFound及原容量release记录恢复评分，不补造旧quiescence文件。

## 明确运行范围

| 项目 | 边界 |
| --- | --- |
| 代码端点 | 固定45份原候选，各最多新评分一次 |
| 交付端点 | 22份PROJECT原证据显示合法提交与代码端点同树；完整原归档／版本链核验后复用各自代码结果，不另创容器。只为不同合法提交树保留最多22个独立身份 |
| 容器上界 | 67，预计同树复用时45；无新数据卷、宿主目录绑定、端口、GPU或模型服务 |
| 并发 | 先REF／PROJECT各1项获得 `official_report` 且 `resolved` 为布尔值；true和false均认可。之后最多4个评分worker，共享原grader lane锁 |
| 单项资源 | 评分容器4CPU／16GiB、network=none、drop ALL；host评分子进程同4核、4GiB地址空间 |
| 管理服务 | 普通用户unit，18核总配额和指定原CPU集合、24GiB总内存、swap0；覆盖最多4个host子进程。无新系统级slice或共享主机配置变更 |
| 异常 | 单题技术未知独立记录。共同的评分配置／来源错误在实际测试前暂停未开始库存；物理清理不明不伪造成功 |

1675与5530仍单列：前者有离线构建依赖及官方测试重置问题，后者有官方测试补丁重命名／重置冲突。它们不被冒称已通过本次manifest修复，也不重复启动相同无效评分。

## 验证与实际状态

最终CPU控制使用4个真实独立 `-m` 子进程，分别执行原 `validate_request` 全路径：普通REF、普通PROJECT、6068精确恢复例外、3536历史候选。真实限制为4核／4GiB；新增污染manifest反例被原validator正确拒绝。没有Docker或模型调用。早期子进程继承私有PYTHONHOME导致encodings启动错误已修复；最终启动清除bootstrap冲突变量。最终证据见 [实际评分子进程控制](../../artifacts/software-benchmark-v095/real-scorer-validation-r2/summary.json)。

首批上线后已产生真实官方布尔回执，REF与PROJECT健康门通过并开放4个worker；这证明manifest修复已进入真实评分阶段。最终统计以 `coordinator/run-summary.json` 与每份 `grading/<key>/receipt.json` 为准，不能把进程退出或score条目存在视为已评分。当前文档不把尚未完成的任务填成失败。

最终计划：[core-rescore-final-r1/plan.json](../../runs/software-benchmark-v095/core-rescore-final-r1/plan.json)。服务：`proworksim-v095-core-rescore-final-r1.service`。前期 `core-rescore-r1` 仅为未获运行授权的准备记录，实际执行使用final目录。

## 最终结果

本批45份均取得可信官方回执：32份resolved、13份未resolved，评分未知0、未开始0。REF为16/22，PROJECT代码端点为16/23。这是指定异常候选集合的补评结果，不是500题总体正确率。

PROJECT的22份原合法交付均通过完整版本与归档核验，与对应最终代码同树，复用同一官方结果；6068代码端点可评分，但原合法交付不存在，仍记录交付为否。没有新增模型调用，也未修改或覆盖旧的技术未知原记录。最终证据见 [补评汇总](../../runs/software-benchmark-v095/core-rescore-final-r1/coordinator/run-summary.json)。
