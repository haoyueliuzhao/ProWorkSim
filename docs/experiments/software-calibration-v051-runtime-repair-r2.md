# v051 CAL2 执行接口的 r2 窄修与必要 CPU 控制

原冻结 `8782bfe` 的首个R槽在任何原生生成准备之前，被新建缺陷工作树的精确身份门拒绝。原112文件的实际UTF-8字节与冻结初态完全一致；读取器却用 `Path.read_text()` 将 `LICENSE` 的29处、`docs/make.bat` 的263处CRLF转换成LF。另一方面，原初态JSON按路径排序，而 `os.walk` 返回目录遍历顺序，项目 `json_bytes` 保留字典插入序；即使保留CRLF，未固定路径顺序的整体JSON SHA仍会不同。这是两项确定的读取/序列化接线遗漏，不是模型修改文件。

第一份只读诊断记录了原始字节全相等、CRLF差异以及raw/source两种SHA，但当时没有进一步解释插入序差异；本修订明确补足这一原因，原诊断不覆盖或回写。原R已经装载权重的worker费用仍保留；它的resident calls为空，prepared/started/complete/fault均0，没有mini模型账单、trajectory或终态guard，R_code继续为null。这份CPU修订不把原槽改写为成功或恢复缺失guard。

原P/U路径另出现独立问题：formal CPU pytest child通过 `proworksim.software_calibration_shell_v051` 导入隔离helper时，先执行了 `proworksim/__init__` 的无关应用依赖闭包，在缺少openpyxl处退出，尚未进入pytest和隔离安装。真实业务评分缺失不能靠修正CRLF归因恢复。原三条已有模型轨迹、成员公开测试和最终评分原件均保留，本次没有补验它们。

## 仅改新主源码

`software_calibration_v051_mini.py` 将初始文件写入改为显式UTF-8编码的bytes，读取改为原始bytes解码；最终返回按路径排序的文件映射。只读元数据确认六个已冻结CAL2初态的文件映射本来均按该路径顺序排列，因此复原原初态JSON身份，不改文件内容、任务或模型提示。原工作树和原冻结源码没有改写。

`software_calibration_repo_tests_v051.py` 同样以UTF-8 bytes物化候选，以bytes比较执行前后的源文件。standalone child按自己 `__file__` 同目录的绝对路径，通过importlib加载原本只依赖标准库的shell模块，不经过应用包初始化。父spec与实际terminal都记录该helper的路径、SHA-256及字节数；child在执行前比较，宿主在判定可信结果时再次绑定。原Landlock/seccomp规则、命令、完整原节点、TCP descriptor fixture、超时、source-attributable collection判据均保持。未安装或更换CPU依赖。

shell模块本身本次未修改。前轮新增的coverage scratch绑定继续保留。修改前完整三个模块及旧summary引用存于 `runtime-repair-r2/first-source/` 和 `first-source-manifest.json`；第一次CRLF改动后的reader版本另存 `reader-first-source/`。

## 两项必要控制及原失败

1. 用修后纯reader读取原R现成工作树，不创建新Git树、世界或模型请求。第一次已经恢复CRLF和112文件逐字节相等，但仍因JSON插入序不同失败；该失败及源码保留。固定路径顺序后，仅重做这一受影响的纯读取，112文件整体SHA精确恢复为 `d5e695c0d3f33c64c417e19f94c6c378a2daaf490aa811d82c55464118f6b73b`，两文件的29/263处CRLF完整保留。
2. 只执行一个新的最小synthetic formal CPU pytest child。生产文件、support、测试和pytest配置均含CRLF；一个测试节点检查生产函数以及实际生产/support bytes。使用原冻结CPU解释器与修后正式runner入口，worker与pytest均退出0，完整terminal和唯一节点齐全，原文件bytes未变，Landlock ABI≥3/seccomp已装，实际helper来源与spec一致，process登记存在。这个synthetic child仅执行一次，没有运行原boltons/parse/xmltodict业务验收。

因此本修订为两项不同必要控制、三次累计控制执行：首次reader失败、修后reader通过、一次synthetic child通过；另有六份既有初态路径顺序的只读元数据记录。原失败没有覆盖。没有重复原TCP、隔离七项、mini循环、六题三态来源资格、SDK或tokenizer控制。新增GPU操作、模型请求、权重加载、反向和参数更新均为0。

所有原件与新独立摘要位于 `artifacts/software-calibration-v051/runtime-repair-r2/`；新摘要名称为 `summary-r2.json`，不覆盖先前准备summary。修订本身不派发任何模型槽，原库存接续须由独立新宿主的来源、预算和例外准入冻结后执行。
