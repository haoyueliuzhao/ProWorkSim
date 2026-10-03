# v0.29 启动快照

北京时间 2026-10-03T23:07:23.136976+08:00，有限实验supervisor已启动。当前状态为 `waiting` / `support`；支持worker尚未启动，真实9B经历0条、参数更新0次、worker GPU小时0。八张卡的最近观察均有其他计算任务，队列等待任一空闲A100满足已冻结的显存与60秒稳定条件。

- 执行提交：`6b90e9bf71455e904e6b1d2b56e2ef59dabbb7be`，独立checkout：`/data1/zhuxinrui/projects/ProWorkSim/runs/v029-frozen-source`。
- 当前源码与资格：`2b6e42e07337f7585ac5d18b63caeacb87d2be103b7f8854cb79f03e817ac2a5`；clean checkout资格通过，测试/控制通过精确字节绑定，不重新采样。
- 实验原件：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-allocation-v029`；supervisor PID `1220919`，finisher PID `1220852`。
- GPU授权范围0–7；没有显存预留进程，没有停止其他任务；不继承累计GPU时长、worker累计时长或统一截止。
- 任务数量、seed与条件上限已在首次模型采样前固定；无支持则结束，技术未知单列，不补采。
- finisher在有限DAG终态生成[真实运行报告](software-allocation-v029.md)及[机器账](software-allocation-v029.json)，只提交这两份结果并按用户授权推送远端。

[完整协议](software-allocation-v029-protocol.md)和[CPU资格](software-allocation-v029-qualification.md)分别说明实现、成本与边界。此快照不是当前模型成功率或ID-VTDO效果结果；后续状态应查看真实运行报告或原始supervisor账。
