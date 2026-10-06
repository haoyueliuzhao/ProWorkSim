# v0.36 启动记录

北京时间 **2026-10-07T00:51:29.491784+08:00** 启动条件实验监督流程；执行源码 `e26ab99df8e555cd144eef2b38641174addb28d7`，隔离工作树 `/data1/zhuxinrui/projects/ProWorkSim/runs/v036-frozen-source`。

快照时间：2026-10-07T00:56:28.666412+08:00。监督状态 `waiting`；9B worker `not_started`、attempted=False；进程与监督心跳已核对。

当前启动快照尚未分配新GPU worker，新增9B调用、actor更新和critic更新均为0，P3尚未开始。队列等待满足连续60秒空闲门，不挤占既有GPU进程、不新增显存预约。此为不可变启动快照，后续状态查运行报告。

## 冻结范围

- 新支持：同9B原完整3／3 common、同sqlparse训练root、新16seed、固定A先手及原共同预算。
- 新Γ与Mapper：有证据的冲突恢复／生产单元保留；结构化成员自测完成语义；旧16条仅作影子开发。
- 贡献开发／独立确认：各4个root×4个seed，试训前冻结用途与清单。
- 用户明确批准自动后续：合格支持→实际全清单冻结→共同B真实消费及成本→完整G-raw／I-P→三个正式分支与独立确认；任何门失败保留原状态并停止。
- 条件上界为592条在线经历、36次完整窗口更新，非已执行数量。原单任务、逐学习段、RSS、GPU与存储保护保持，无累计GPU／worker／统一墙钟硬上限。

## 证据入口

[完整协议](software-support-v036-protocol.md) · [准备记录](software-support-v036-preparation.md) · [启动机器快照](software-support-v036-launch.json)

[P2运行报告](software-support-v036.md)／[P2机器账](software-support-v036.json) · [P3运行报告](software-allocation-v036.md)／[P3机器账](software-allocation-v036.json)

本次修订已提交并推送；运行结束自动归档及提交推送。CPU程序控制、tiny更新、真实支持与真实参数收益分别报告。
