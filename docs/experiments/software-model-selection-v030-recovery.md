# v0.30 加载记录故障恢复与GPU5交接

2026-10-04用户要求“5号卡有空闲，尽快抢占”。检查发现旧三候选队列已于北京时间**19:09:16.927**结束：9B完成12条开发筛选，两个新模型均在写加载记录时因JSON序列化异常退出。旧批次的`finite_batch_no_qualified_candidate`是当时真实程序终态；两新模型没有开始资格推理，不能据此判定模型推理、训练或软件工作能力不足。

本次在保留旧原件的基础上修复这一明确接入错误，建立一次有记录的恢复尝试。9B的12条结果全部继承，不重新采样；两新模型仍各最多12条正式开发筛选。旧加载失败原件和成本保留，恢复不追加模型、不改seed、不降低概率、近16K容量、工作验收或选型门槛。

## 准确故障与修复范围

Transformers 5.17的`LoadStateDictInfo.to_dict()`返回`missing_keys`、`unexpected_keys`、`mismatched_keys`等set。两个新模型已通过架构、EOS、LoRA、实际存储dtype/device及缺失/多余tensor检查，且已构造owner、写出generation contract；随后在`candidate_runtime_v030.py`写`resident/dense-loading.json`时，即使空set也会触发`TypeError: Object of type set is not JSON serializable`。

修订只把加载诊断中的顶层set转换为确定性排序数组，并另记原容器类型。原非空加载错误拒绝条件、主干/LoRA精度、原生格式、概率和更新路径不变。不将set笼统转字符串，不丢弃加载错误。

| 原尝试 | GPU时间 | 真实原生调用 | 正式筛选 | 参数更新 |
|---|---:|---:|---:|---:|
| SWE-Next-14B加载失败 | 15.887841秒 | 0 | 0 | 0 |
| Devstral-Small-2507加载失败 | 20.620105秒 | 0 | 0 | 0 |

零调用的证据是两臂均无qualification/native response、无common checkpoint和screen目录，resident calls目录为空，owner policy revision为0，report rows为空。这里是完整检查本次落盘文件后的判断，没有把日志缺少某个词单独当作零调用证据。两次失败合计**36.507946 GPU秒**，恢复成本账保留这些已发生消耗。

旧9B已通过全部技术资格及近16K实际完整反向，正式筛选API2/4、修复4/4、O1 0/4，未达到各类别至少2/4的门槛。其原worker耗时7,028.481027秒；诊断更新后已完整恢复，正式筛选优化器步数0，最终仍为actor/critic 3/3。这些结果及原source身份原样保留。

## CPU证据继承

恢复资格不冒称原71项测试及18组合原生矩阵在新提交上重跑。新增检查覆盖空set成功序列化、非空错误与原类型保留，以及恢复队列的旧结果继承、一次恢复范围和预约交接。原有已验证源码、脚本与测试逐项核对hash；唯一变化的backend通过AST比较确认：移除新增诊断表示函数及唯一`dense-loading.json`写出表达式后，新旧模块完全相同。

[恢复资格绑定脚本](../../scripts/qualify_model_selection_recovery_v030.py)要求干净执行快照、新增定向检查通过、当前源文件与检查证据完全一致，再将原CPU资格和这次局部修复证据绑定。原CPU记录保持原source/commit，不回改历史结果。恢复worker仍通过原strict plan验证并执行真实模型资格，局部CPU修复通过不能代替这两模型的实际训练资格。

最终必要控制为**8项通过、8项未选中**（8.83秒）：6项恢复机制检查加2项序列化检查；全范围Ruff通过。原生矩阵和旧71项测试没有重复。命令、stdout、文件SHA和原件引用见[恢复控制记录](software-model-selection-v030-recovery.json)，被测源码树SHA为`a04ad0117628ae41aa3cdfee9a09c1d0f7a8d963c9acf4b0538fbeadc7b9059a`。

## GPU5预约过程

最初检查时GPU5为0显存占用；首次预约在CUDA分配前发现可用显存已低于门槛，退出且未持有显存。随后观察到另一作业占用该卡，未终止或修改该作业。

另起的CPU预约进程每秒检查GPU5的UUID、空闲显存、利用率及compute PID；仅当整卡满足空闲条件时启动独立分配进程。该卡再次空闲后，于北京时间**20:27:03.530**成功保留**76 GiB**：分配PID2945865，start ticks354121613，GPU UUID`GPU-f731a280-01e3-2359-ace9-aa2ad2112f55`。父预约进程PID2938959；分配后每2秒保存心跳和只有自身compute PID的观测。

预约原件为`runs/v030-recovery/gpu5-reservation-r1/`，首次失败保存在同级`gpu5-reservation/`。恢复交接必须核对预约PID、启动ticks、UUID、连续空闲/独占观察及新鲜心跳，使用pidfd只释放本次拥有的分配进程，随后立即启动模型，不在释放后重新空等60秒。GPU5优先；既有八卡可用授权保持。预约显存占用单独记账，不算模型工作GPU秒或训练成绩。

## 原件与结束条件

原批次目录`runs/software-model-selection-v030/`及其已推送报告提交`d2766791b094b23603835f209416b63b6d033c06`保留；旧终态报告副本另存`runs/v030-recovery/original-final-report.md/.json`。新恢复使用独立输出目录，原9B通过明确旧路径与SHA继承，两个旧加载失败不会被覆盖为成功。

本次恢复只重新启动这两个尚无模型调用的新候选，最多各一次。实际推理/训练资格失败仍按协议停止该臂；不无限重试，不把技术未知补成工作0分。最终把原9B和两次恢复结果按原选择规则汇总，报告同时列出原失败与新worker成本。整批完成后自动更新实验报告、提交并推送，不自动启动未冻结的B/G-raw/I-P。
