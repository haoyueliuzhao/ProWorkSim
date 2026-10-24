# v056 REF 驻留扩展至六卡 r2

2026-10-24（Asia/Shanghai）。按已冻结计划的最多六个生成回合上限，在首批GPU0/1/2/4四个服务之外，为GPU5和GPU6各增加一个相同REF驻留。派发前逐卡当前空闲显存均为81,152MiB，通过原66,560MiB容量门与UUID租约；没有要求整卡空闲，也没有停止其他使用者。

| GPU | 新服务 | loopback端口 | ready后显存占用／剩余 |
| --- | --- | ---: | ---: |
| 5 | proworksim-v056-ref-gpu5-r1.service | 18061 | 63,249／17,903MiB |
| 6 | proworksim-v056-ref-gpu6-r1.service | 18062 | 63,249／17,903MiB |

两个服务均已完成认证ready，宿主PID/start_ticks与ready身份一致，没有closed标记。均使用systemd用户管理器、Restart=no、KillMode=control-group、CPUQuota1200%、MemoryMax96G、TimeoutStopSec60。服务归属仍各自保存在resident目录的service-unit.json及service-launch.json。

本次没有修改已冻结服务代码、模型／数值设置、预算、题单或队列绑定，没有重载原四个resident。追加组件没有自行派发正式槽或发送模型生成请求；已运行队列可按原规则自动拾取新ready服务，受共同最多六生成和CPU／磁盘门约束。

独立补充凭据：[ref-service-expansion-r2.json](../../artifacts/software-benchmark-v056/ref-service-expansion-r2.json)。原四卡r1启动证明保留，未覆盖。实际任务吞吐与成绩仍以队列逐槽记录为准，不能仅由六服务ready推断已经同时运行六个回合。
