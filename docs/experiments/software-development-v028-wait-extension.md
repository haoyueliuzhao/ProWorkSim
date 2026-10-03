# v0.28 等卡延长与八卡候选调整

2026-10-03，用户明确要求将原等待截止延长两天，并将八卡全部纳入排队范围。等待截止由北京时间2026-10-04 00:00延至2026-10-06 00:00；最终墙钟截止同步由10月4日03:05延至10月6日03:05。

候选卡由GPU0/4/5/7扩展至GPU0–7；原空卡、空余显存至少78000MiB、利用率≤5%、连续60秒的准入条件继续有效。同一8个槽、两worker各10800秒、累计21600 GPU秒、最多两模型实例并行、零参数更新和不自动重试的边界保持有效。这是排队配置调整，不代表增加模型样本、训练轮次或GPU预算。

旧监督43475（start_ticks=338611052）暂停后核验所有worker未attempted、无worker目录、累计GPU秒0。旧归档驱动43411（start_ticks=338611027）先终止，避免发布过时状态；再让旧监督正常处理SIGTERM并保存终态`supervisor_interrupted`。终态仍为全部未启动、GPU秒0。原队列、计划、资源轮询和启动信息均原位保留，路径不改写。

过渡证据保存在`runs/v028-wait-extension-20261003/transition.json`。旧队列位于`runs/domain-v028-software-dev/`，旧声明位于`runs/v028-declaration/plan.json`。旧finisher文件是终止前的最后快照，其进程终止事实以过渡证据为准。

本次修改runner的候选卡及默认期限，并修正只读报告从实际计划读取卡范围和日期，避免后续自动报告重新写回旧四卡/旧期限。相关8项测试和修改文件静态检查通过。

截至北京时间 **2026-10-03T14:46:35.007991+08:00**，新监督状态为`waiting`，全部8槽未启动，累计GPU秒0；模型结果仍未知。新归档驱动PID **728914**、监督PID **728921** 均核对存活及启动身份，监督心跳距核验约4.9秒，实际监督载入的新计划SHA与声明一致。

新冻结源为`b55364376d119f4767cb58c17e8fc3926bb49627`，工作树`runs/frozen-v028-wait-extension/`。本次只改排队和只读报告脚本，模型与工具执行逻辑未改；src树摘要与原冻结源相同。由于完整冻结提交变更，仍按现有启动校验重新保存了同源CPU/SDK/tokenizer资格：4/4程序控制通过、58次程序请求、模型调用0，最大prompt7660、最大程序输出635，扣除2048输出预留后的最小余量6676。资格期间源码未改变。上述是程序控制及tokenizer测量，不是模型运行结果或学习效果。

当前有效路径：

- 计划与过渡证据：`runs/v028-wait-extension-20261003/plan.json`、`transition.json`、`launch.json`、`verification.json`。
- 当前模型队列和逐槽原始轨迹：`runs/domain-v028-software-dev-wait-extension/`。
- 当前归档驱动状态：`runs/domain-v028-software-dev-wait-extension-finish.json`。
- 新冻结资格：`runs/v028-controls/frozen-sdk-tokenizer-wait-extension-20261003/`。
- 原始归档驱动日志：`runs/v028-wait-extension-20261003/finish.log`。

旧队列目录`runs/domain-v028-software-dev/`为本次调整前历史，已停止，不再是实时运行入口。两个队列合计仍只有8个可执行槽和21600 GPU秒预算；旧队列零启动，因此没有重置已消耗预算、重复采样或重试失败模型经历。空卡稳定计时在新监督中重新开始。

新归档驱动沿用实验结束后自动汇总、仅提交推送两份运行报告的行为；修改后的报告从其实际计划显示八卡范围和新日期。原计划、原监督终态、原资源轮询和启动信息的摘要在核验时均未改变。全部过渡记录和实际加载计划见[机器证据](software-development-v028-wait-extension.json)，实时最近报告见[运行报告](software-development-v028.md)。
