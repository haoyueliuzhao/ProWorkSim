# 原v0.15筛选结案（v0.17时读取）

三条原线都已完成全部36次尝试，没有重采。27B的14个未知episode保留，不能为原三模型形成完整评分排名。原后继观察器因此在选型前停止，N0/N1及软件后继均未启动。

| 候选 | 已知/未知 | 已知完整成果 | 原全批平均R |
|---|---:|---:|---:|
|qwen25-7b|36/0|0|0.1138888888888889|
|qwen35-9b|36/0|3|0.27222222222222225|
|qwen38-27b|22/14|11|None|

27B的18次实际CUDA OutOfMemoryError导致14个episode不可评；另外1次在生成前触发context_length_exceeded。这不是同一类别，后者的已知无生成合同不自动造成未知奖励。GPU内的逻辑cuda:0对应原CUDA_VISIBLE_DEVICES的第一卡（物理1），不能把报错GPU0错归为9B的物理0。

完整任务、事实、重复及每条原始闭合证据引用见[v017-original-s1-report.json](v017-original-s1-report.json)，所有错误原文及容量probe事先选取规则见[errors](v017-original-s1-errors.json)，成本见[resources](v017-original-s1-resources.json)。机器可读压缩报告不重新评分；未压缩原报告仍保留于runs并由SHA绑定。

新H1单独修订原S1准入：三臂全部尝试并闭合，不要求把未知变成已知；保留实际S0数值资格和全部未知，不沿用原线selected。新9B两卡/27B四卡，在各自两harness之间相同，先以固定长请求核定推理容量。旧3卡27B、1卡9B结果保持原数值和资源解释，不当作新配置的成绩。
