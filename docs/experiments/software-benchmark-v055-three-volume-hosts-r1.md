# 九组实验三卷宿主适配（2026-10-22）

本修订增加新 DeepSeek 生成回合可使用的第三块独立文件系统，继续保留 Qwen 主盘生成与 REF 完成后的显卡接力。它只调整未来 pending 槽的宿主磁盘派发，不移动在途目录，不更改题单、seed、模型、提示、工具、预算、采样或官方评分规则，不重载模型。

## 固定来源

三卷公共清单为 `runs/software-benchmark-v055/three-volume-admission-r2/volumes.json`，SHA-256 `e63806b732f40ecc4c8c85cf7c6710e28a1eac118a292a64135ba31de3092e2a`。公共helper为 `src/proworksim/software_benchmark_disk_volumes_v055_r2.py`，SHA-256 `df117c1ec357ef4cab207aca61aa91b16164096adfc82d9c0f80bf6169a205fe`。

| 用途 | 路径与真实设备 |
| --- | --- |
| primary | 原项目和运行目录；device 66306 |
| secondary | `runs/software-benchmark-v055/secondary-volume-r1`，原 data1 独立卷；device 66307 |
| tertiary | `runs/software-benchmark-v055/tertiary-volume-r1`，bind 源 `/data2/proworksim-zhuxinrui/v055-spare-volume-r1`；device 66308 |

helper 沿用原阶段预约与共享 flock 身份，按运行记录的绝对目录和实际 `st_dev` 给三个卷分别计入尚未发生的增长预约。每次准入核查三卷登记、原marker、mountinfo与设备；身份不明或挂载丢失时拒绝准入，不降级写入挂载点下面的主盘目录。可用字节显式使用 `f_bavail*f_frsize`，另报 `f_bfree` 与文件系统保留块；本机原 `shutil.disk_usage().free` 已经采用相同可用字节口径，本修订不声称修复旧版保留块误计。

## Qwen r6

新入口 `tools/run_qwen_three_volumes_v054_r6.py` 直接继承当前 `run_qwen_ref_handoff_v054_r5.HandoffCoordinator`。原 r5 的 REF→MATCH/PROJECT pool overlay、generation worker wrapper、GPU6 snapshot 路由、recovery adoption 和旧 resource planning 身份保留。父构造器仍绑定原 r5 revision；随后只在当前新宿主进程内将磁盘 facade 替换成三卷helper。新 `three_volume_host` 状态和独立 adoption 回执记录此次宿主修改，原正式 rows 不改。

Qwen 仍在 primary 生成，但能够识别已经位于 tertiary 的 DeepSeek 活动预约，不会把已登记的第三卷误判为未知设备。新修订不再次执行旧 recovery adoption，不触碰已有worker或resident GPU服务。

冻结回执：

- `runs/software-benchmark-v054/three-volume-host-r6/revision.json`
- SHA-256：`8cb5b42cd6b9c49e4709cfb2581032b30e5e00abb00fd3fdc7d273193fdec961`
- 精确前驱：`ref-handoff-host-r5/revision.json`，SHA `b579c732e93c642d8213d09d60a052180774f45e85ba9b2c154d7ca6a5ed81dd`。
- 交接时只允许原 `proworksim-v054-formal-queue-ref-handoff-r5.service` 协调器已停止；不在此工具内发送停止信号。

## DeepSeek r9

新入口 `tools/run_deepseek_queue_native_host_v055_r9.py` 使用独立 `software_benchmark_queue_native_host_v055_r9.py`。它继承原 r8 初始化、r4 BudgetLedger、all-arm财务适配、PROJECT的materialize配置与direct命令包装，以及原native r3科学activation。原请求上限、2000元总预算、网络隔离、并发硬门和评分路径保持。

每个新generation严格按以下顺序执行：

1. 确认原记录仍为 `pending`，获取原跨宿主共享磁盘锁。
2. 按相同slot ID导出原worker后缀，检查primary、secondary、tertiary三个位置是否已有目录或symlink。任何既有pre-intent痕迹都进入原延期集合，不通过换卷重跑。
3. 在锁内读取当前三卷身份、活动预约和准备任务需求。primary仍须满足原共享基础设施空间下限；两个生成卷各自扣除活动预约、新回合预计增长后，必须保留原100GiB底线。
4. 在通过准入的secondary/tertiary中选择剩余可用空间更大的一卷；完全相等时固定优先secondary。选择仅依据容量，不读取题目成绩。
5. 只在调用冻结的原r2 worker builder期间更改generation根目录。r8的财务包装context已经安装，PROJECT和其他组继续使用同一财务适配。原builder的持久intent保存与systemd启动均在同一个共享锁内完成，随后恢复primary宿主根。

`state_path`、coordinator锁、账本、评分、预热、共享cache均留在primary；所有在途worker按其已记录的绝对路径继续收集。不同host的源码和revision均独立封存，没有热改旧r8或已生成的worker配置。

必要窄保护将单题template估算的 `OSError/ValueError/KeyError/TypeError` 记录为明确的本地元数据技术异常，调用既有defer并继续其他行，不调用模型builder，不把未知记为代码失败。共享卷身份/快照异常则保持公共派发gate，不归为单题结果。这避免增加选卷逻辑时让一项坏manifest导致协调器退出。

冻结回执：

- `runs/software-benchmark-v055/native-host-revision-r9/revision.json`
- SHA-256：`ecb60e422eb856527112bb66452f03aa28097b5ede79fb58648feeb5d7638bf2`
- 精确前驱：`native-host-revision-r8/revision.json`，SHA `c4837307e41735fd8ae9e1b53fe62fb362bedf871e8dd31fa76edca89c011107`。
- r9实现SHA：`afbf21cbd9c5e9db4437dcd7034756d068908bbd29318bb7b70b90a9799fe3ba`。
- 原 `proworksim-v055-deepseek-six-conditions-native-host-r8.service` 仅由独立交接操作停止，工具本身不停止worker或服务。

## 验证与报告边界

13项纯CPU内存控制通过，涵盖按扣预约后余量选卷、固定tie顺序、primary和两个生成卷空间底线、身份错误拒绝、三处preintent阻断、同锁保持到原builder、PROJECT预算字段、r8财务activation继承与Qwen原r5 worker route继承。随后独立审阅发现template估算异常可穿透旧tick的问题；仅补该处保护并追加3项控制，确认坏manifest无builder/宿主退出、后续pending题仍派发、root/target/arm恢复。旧13控制绑定修改前源码，新增3控制绑定最终源码，两份原件分别保留，不假称整套重跑。限定三个新文件Ruff检查通过；审阅者只复核已指出的异常点，没有重复整套检查。

第三卷真实零模型lifecycle回执为 `tertiary-volume-r1/host-lifecycle-match-r1/volume-control.json`：一个真实clone、程序响应、导出/静止/清理闭合，real API、GPU、正式claim和grader调用均为0。原首次尝试在clone前因新空目录的setgid位不符合0700而拒绝，原失败及mode-correction另存；第二次通过。该控制证明第三卷文件系统生命周期，不是完整模型能力或吞吐测试。

控制与小型冻结回执保存在 `artifacts/software-benchmark-v055/three-volume-host-control-r1/`。主代理已完成正式交接：北京时间16:14:31启用Qwen r6，16:14:48启用DeepSeek r9；只停止旧协调器，原worker和驻留模型继续。主代理16:15:01的现场快照显示DeepSeek共有27个running回合（secondary 20、tertiary 7），达到当时desired27，`metadata_error=null`、`dispatch_stopped=false`；Qwen仍有7个回合运行。

这一次快照证明新卷已经承接真实新generation并填补当时的派发缺额，不能替代持续吞吐测量。单位时间完成数、尾部耗时和ETA需由后续独立监控给出；本记录不把瞬时并发提升直接换算为同倍数速度提升。具体交接与旧活动路径身份保持证据由主代理另存；实现代理没有启动或停止服务。
