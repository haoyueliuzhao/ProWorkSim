# v049 r2g 执行与资源回执窄审计

结论：通过。冻结源 `9d8a8f753de15b30f51b771f90184f69d5dd4831`；仅审阅已保存回执，没有模型、GPU查询、分词、测试、业务验收或张量读取。

| 原槽 | 物理 GPU | PID / start_ticks | 装载前空闲 MiB | 60秒门证据下界 | 运行采样数 | worker 驻留秒 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| dev-B-DB-s1 | 0 | 3395337 / 424261672 | 72623 | 60.841489 秒 | 38 | 251.852722883 |
| dev-B-DB-s2 | 1 | 3395345 / 424261677 | 73077 | 60.841489 秒 | 40 | 265.048489094 |

两 worker 的实际命令和宿主命令均为 r2g；GPU UUID、PID 与 start_ticks 在装载及运行回执中一致。两者装载同一原 B4/4，源提交前后相同且 clean，新增 actor/critic/backward 均0；终态 collection guard 的学习状态摘要相等、Torch RNG 精确恢复。

等待10次采样均满足原57344 MiB门，保守样本跨度 60.841489 秒；最大驻留3和原其他门保持。运行采样没有 guard停止、陈旧数据或失败记录；mechanism-stops、host-stop-actions 均0。两卡是共享设备，整卡利用率不得归因到本实验。

原 r2 等待根精确8文件均与新plan冻结摘要同字节，仍为 interrupted、两槽零attempt/worker/PID/目录、零GPUworker成本。新两worker合计 516.901211977 秒（0.143583669994 小时），此数是宿主启动至关闭的驻留时间，不是GPU实际忙碌时间或利用率。

审计限制：内部stable字典精确写入时间未存档，使用连续合格采样的保守跨度；显存与身份仅对保存的离散观测成立。B状态依据原JSON回执和collection摘要，未重新读取`.pt`。未重复979旧源逐字节审计，仅核对本轮四个新增冻结文件与执行源回执。报告中的R=1/1是已有结果绑定，没有补验业务。原DA-s2未知与F_B=null保持。

机器凭据：`/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-learning-v049/analysis/r2g-execution-resource-audit.json`，SHA256 `a6bf1f8f224c032a8a57c77b964afde5958f64565152dade8d9efcac394de512`。检查项 55，失败 0。
