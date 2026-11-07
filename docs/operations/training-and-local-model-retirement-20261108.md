# 停用训练与本地模型：2026年11月7—8日清理记录

按用户授权，本次删除不再使用的本地模型权重、训练检查点及明确用于训练的原始数据，保留评测记录和当前API、导出、评分所需环境。后续不开展训练，也不自动重新下载已退役的本地模型；后续安排以用户新的明确指令为准。

两批操作实际删除 **36,762个文件，合计141,556,461,568字节，约131.834728GiB**。这里统计删除前各文件的`st_blocks × 512`，不是共享文件系统`df`空闲空间的前后差值；服务器其他任务的写入或回收会影响后者。审计汇总及各批plan、事件、receipt的SHA见[清理汇总](../../artifacts/software-benchmark-v153/training-retirement-r1/summary.json)。

## 完成时间与范围

时间均由实际receipt的`finished_unix`转换为北京时间（Asia/Shanghai），不是按文档文件名推定。

| 批次 | 实际完成时间 | 删除文件数 | 删除前分配字节 | GiB |
| --- | --- | ---: | ---: | ---: |
| 本地权重、训练检查点及下载残留 | 2026-11-07 23:46:11 | 353 | 124,906,852,352 | 116.328571 |
| 明确训练用途的原始数据 | 2026-11-08 00:02:37 | 36,409 | 16,649,609,216 | 15.506157 |
| 合计 | — | **36,762** | **141,556,461,568** | **131.834728** |

两份[第一批receipt](../../runs/storage-retirement-v153/model-and-checkpoint-r1/receipt.json)、[第二批receipt](../../runs/storage-retirement-v153/training-raw-r1/receipt.json)均记录：计划删除路径已不存在、受保护元数据保持不变、错误列表为空。两批都由普通用户UID 1021执行，`root_operations`、`services_stopped`、`host_configuration_changes`及`model_calls`均为0。

## 第一批：四份本地模型与训练产物

实际删除的24个下载权重文件属于以下四份本地模型。版本列采用原下载清单或本地快照的revision前12位；完整来源标识、文件名、原stat及删除事件保存在[第一批plan](../../runs/storage-retirement-v153/model-and-checkpoint-r1/plan.json)及其审计链中。

| 模型 | 本地版本标识 | 权重文件数 | 分配字节 | GiB |
| --- | --- | ---: | ---: | ---: |
| TIGER-Lab/SWE-Next-14B | `5d9484d6b0e2` | 6 | 29,540,167,680 | 27.511425 |
| Qwen/Qwen3.5-9B | `c20223623576` | 4 | 19,306,336,256 | 17.980427 |
| mistralai/Devstral-Small-2507 | `bd165ab26ceb` | 10 | 47,144,923,136 | 43.907131 |
| Qwen/Qwen2.5-7B-Instruct | `a09a35458c70` | 4 | 15,231,295,488 | 14.185249 |

SWE-Next和Devstral的原清单另记录了ModelScope权重revision，分别为`9a2331e309eba573dace3c20f6bc80c05067563b`与`fd677dc8b6f1abd36f93342a552529b686439b66`。这些来源记录继续保留；表中的本地版本标识不把两个下载源的revision混为一个值。

第一批还删除319个训练检查点、适配器或梯度载荷文件，共3,372,756,992字节；8个上述模型私有目录内的未完成下载缓存，共10,297,049,088字节；以及2个下载训练数据文件，共14,323,712字节。后两份训练数据是`runs/assets/sql-v020/six/train.jsonl`与`runs/assets/sql-v020/critic/sqlite-00000-of-00001.jsonl`。

模型配置、分词器、来源清单及checkpoint描述元数据保留。四个模型目录均写入`MODEL_WEIGHTS_REMOVED.json`，明确当前权重已删除、不可加载，原下载完成清单仅是历史记录。两个受保护的小型验证夹具文件——`runs/v015-runtime/tiny-multigpu-checkpoint-r2/`下的共享状态及适配器——被明确跳过，未计入删除量。保留这些夹具和环境不意味着重新允许训练。

## 第二批：按明确训练用途删除原始数据

第二批采用逐文件白名单，合并主清单与额外domain清单后执行；没有整棵删除`runs`或凭目录名猜测`common`用途。

| 原始数据类别 | 文件数 | 分配字节 |
| --- | ---: | ---: |
| domain-v023训练回合、调用及批次输入 | 4,098 | 2,964,234,240 |
| domain-v024／v025／v025-r1额外训练数据 | 1,992 | 1,770,057,728 |
| software-learning-v049／v050及训练续跑的回合、调用、训练entry | 11,032 | 5,466,324,992 |
| learning-v014 MC／RTG明确训练窗口原始样本 | 19,211 | 5,719,064,576 |
| 仅包含训练单文件内容的历史压缩对象 | 76 | 729,927,680 |

纳入内容包括明确训练回合下的episode、模型调用、投影、运行轨迹，以及训练window的`entries.json`、更新阶段的大型`admission.json`。v014通过小型`window-spec.json`核对：只有`mode=online`且window ID明确为train的窗口进入清单；9个虽然位于`collection`目录、实际为evaluate的窗口被保留。

domain顶层6—9KB的`admission.json`属于来源与窗口合同声明，`composition.json`属于组成说明，均保留；删除的是更新阶段实际承载训练批次的大型admission载荷。软件训练续跑的composition entries仅在来源注册表全部指向`org49-train-*`或`org50-train-*`时纳入。

76个压缩对象均有单文件验证记录，且其内容组涉及的全部原路径均被分类为训练数据；本次对象为gzip。多用途归档不按训练归档处理。原归档sidecar、verified记录和plan继续保留，作为历史来源证据；其指向的已删除训练对象不能再据旧索引恢复。

## 保留的评测材料与运行依赖

评测、开发、确认和外部测试材料保持，`software-benchmark-v054`及之后的评测记录、补丁、评分结果和证据链不在训练raw删除范围内。源码、报告、summary、protocol、manifest、配置及checkpoint元数据继续保留。

当前API与评分依赖也保持，包括项目`.venv`、`.train-venv`、`runs/v016-sdk`、`runs/v015-runtime`，DeepSeek分词器及其overlay（`runs/software-benchmark-v055/tokenizer-r1/`），v146运行包，以及当前v149／v150／v151／v154导出和评分目录。运行解释器和评分sysroot保留；本次没有停止服务、重启Docker守护进程或修改共享服务器的挂载、网络、驱动、cgroup配置。

删除按普通用户拥有的精确文件进行，执行前保留占用检查及文件身份记录，执行结果逐项留档。有关“保护评测”的结论以本次白名单、排除规则及receipt为依据，不将目录级总容量变化当作逐文件证明。

本次是载荷退役。历史模型清单中的下载完成状态、旧检查点引用或训练归档索引仍反映当时状态，并不表示相应权重和训练样本当前仍在磁盘上。后续检查本地可用性应同时查看本次删除审计，不能因发现历史引用而自动下载模型、恢复训练或补造已删除的原始轨迹。
