# v051 CAL2 R 权威评分树

本实现只用于R原生执行器的终态代码评分，不改变P/U世界的文件权限，不重做原来源或初态资格。正式实现为`src/proworksim/software_calibration_native_grade_v051.py`；宿主使用`grade_native_candidate(provider=..., task_id=..., candidate_files=..., run_root=...)`。

`canonical_grading_tree`保留原始候选不变，并另建评分树。原测试、配置、文档及其他非editable支持文件全部恢复为原始字节，包括被候选删除的文件。原editable生产文件的实际修改与删除保留。新增生产文件限于boltons包内合法标识符路径的`.py`，或parse/xmltodict仓库顶层合法标识符命名的`.py`辅助模块。新增conftest、pytest配置、构建/测试配置与Python启动定制入口被排除，其余新增非生产文件也只保留在原候选中；原先不存在的配置不会被带入权威评分。

评分记录逐项列出接受的新增生产文件、真实删除的生产文件、修改或删除后恢复的readonly文件、排除的新文件，并绑定初态、候选和评分文件树各自SHA。`raw-candidate-files.json`、`grading-files.json`、`canonical-tree-receipt.json`、`runner-task.json`、`runner-receipt.json`与`terminal-code-assessment.json`写入独立不可覆盖的评分目录。

执行使用provider注入的同一共享runner，固定原nodeid清单，传入完整初态路径和合法新生产路径，最多调用一次。它不经过P/U的固定文件集校验，因而不会误禁R允许的新增或删除。已知普通结果必须同时绑定runner身份、输入树SHA、原节点SHA、源与测试完整性、worker正常退出、无超时及节点清单。收集失败另须保留全部归因证据，且只接受已绑定的pytest2/4；来源失配、运行器中断、环境故障或不足证据保持`R_code/Q_task=null`。

`Q_task`为原完整固定分母中已经证明通过的节点比例。充分绑定的生产代码收集失败中，未运行节点记为`not_run_due_to_code_collection_failure`、`node_outcome_observed=false`，不能声称其测试体运行失败。原生`R_code`与P/U项目固定提交R保持不同端点。

本次仅执行3项新增纯CPU/假runner控制，共5次程序给定runner回执，检查生产增删与配置恢复、单次调用/部分得分，以及绑定收集失败与未绑定/来源失配/worker中断的区分。3项全部通过，Ruff通过。最初工具启动被bwrap阻断，发生在pytest/Ruff执行前；随后仅执行一次实际控制组。控制摘要为`artifacts/software-calibration-v051/native-grading-controls.json`。真实仓库pytest、旧资格重跑、SDK请求、分词、模型、GPU与HOLD任务读取均为0。

随后的窄边界修订允许原始候选为空：模型删除整个工作树时，仍恢复原readonly，并保留所有生产文件真实删除，不能先误报为非法候选。只在原canonical控制加入这一反例并重跑变更的1项，通过；另2项与5次假runner调用直接复用。最终仍为3项唯一控制、累计4次控制执行，Ruff通过。最终摘要为`artifacts/software-calibration-v051/native-grading-controls-r2.json`；首版摘要及与其SHA匹配的首版源码另存，未改写。
