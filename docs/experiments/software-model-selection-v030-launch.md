# v0.30 三候选队列启动记录

北京时间**2026-10-04 13:54:31**启动独立监督与收尾进程；**13:59:04**在GPU4启动当前9B的真实worker。14:01:16观测时，9B已加载、恢复原actor/critic累计3/3完整状态并进入真实技术资格；SWE-Next-14B和Devstral-Small-2507仍处于`waiting_download`，没有为下载等待占用GPU。正式36条开发筛选尚未开始，当前不能报告候选排名、完整工作通过率或分配收益。

此页是固定启动快照；完整运行变化及整批终态见[运行报告](software-model-selection-v030.md)。对应[结构化启动证据](software-model-selection-v030-launch.json)保存下列原件的当时完整值与SHA，原路径后续仍可更新，不把启动时的hash当成可变状态文件的永久hash。

## 冻结与进程

执行提交为`c1c8a5e7d2386781cc1bd5233d3659d0a4328f87`，源码树SHA为`d0331a942b14ed7e23018c37ba7d64de0b6a69f8edbb1c427fd766b408ef7774`。源码位于独立干净工作树`runs/v030-frozen-source-r1`，不受main上后续报告更新影响；执行快照内没有人为添加venv或runs符号链接。

最终CPU绑定原件为`runs/v030-controls/frozen-qualification.json`，`passed=true`、`code_dirty=false`、`model_calls=0`，与执行计划严格同源。首次辅助脚本的引用字段错误在GPU启动前发生，修订原因、未变文件证据和原失败快照保留，见[CPU记录](software-model-selection-v030-cpu.md)；没有以旧dirty资格绕过启动门。

| 项目 | 启动身份／原件 |
|---|---|
| 固定计划 | `runs/software-model-selection-v030-plan.json` |
| 独立收尾进程 | PID2322147，独立session，`runs/software-model-selection-v030-launch.json` |
| 监督进程 | PID2322214，`runs/software-model-selection-v030/supervisor.json` |
| 当前9B worker | PID2327267，GPU4，`qwen3.5-9b/state.json` |
| 执行总目录 | `runs/software-model-selection-v030/` |
| 收尾日志 | `runs/software-model-selection-v030-finisher.log` |
| 独立下载进程 | PID2249361，`runs/v030-models/range-download-launch.json` |

进程身份还保存启动ticks；PID仅用于记录，不授权按同一数字终止后续其他进程。排队初期八卡有其他compute进程；随后GPU4释放，经连续60秒满足空闲门后才启动9B，未停止其他作业。以后每个候选也须独立满足相同资源门。

## 下载观测与自动接续

14:01:16读取的清单：SWE-Next已持久化范围为9,395,240,960字节，Devstral为9,563,013,120字节，两个清单均仍为`downloading_weights`。这些是range journal确认进度，不是已完成分片，也不是预分配文件的逻辑大小；清单的观测时间保留在JSON中。没有据短期速度给出完成时间承诺。

下载并行度固定每模型4个文件、每文件8个range。HF官方revision与ModelScope固定revision的16个分片逐项SHA/size对应，只传一套Transformers权重；下载后全SHA完成才发布`complete`。旧传输前缀保留并单独记账，不计入已验证range。下载失败会让该臂终结，其他臂继续，不替换模型。

监督进程按[冻结协议](software-model-selection-v030-protocol.md)执行每臂真实推理、概率、完整反向、一次诊断更新、保存重载、新身份回流与共同状态恢复；仅全部必要资格通过后进入12条冻结开发筛选。当前推理输出或单项资格通过不能预支完整训练资格，更不能记作业务训练收益。

三个固定候选全部终结后，独立finisher运行报告脚本，只提交`software-model-selection-v030.md/.json`两个报告文件并推送既有`origin/main`。main分支如发生变化则记录未发布原因；不会改写实验快照、追加候选、重试失败臂或启动未冻结B/G-raw/I-P。该后续提交沿用用户已授权自动提交推送，不依赖当前交互窗口持续开启。

## 最初真实调用观测

9B前三条资格调用的实际输入／输出token数分别为562／28、8,181／50、10,224／50，原生接口与完整trace检查均通过，`inference_ready=true`。第四条压力请求为14,332／2,048，合计16,380 token；输出自然达到预定上限，工具block未闭合，按事前协议保存所有原始token，不用这条输出语法决定前三项接口门，也不裁尾重判。它是近16K实际长度证据，仍须完整反向成功才满足容量资格。

随后已进入完整trace概率重算与聚合诊断更新阶段。记录时`training_ready`尚未完成，不提前报告训练接入、保存恢复或开发筛选通过。此阶段原始报告另存入启动JSON的`early_real_qualification_observation`，与最初14:01的排队／装载快照分开；最新完成情况仍以运行报告及原始资格终态为准。
