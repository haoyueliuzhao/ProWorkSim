# v057 共享服务器事故后的实验硬暂停

`config/v057-shared-server-hold.json`目前固定为`hold=true`。即使宿主挂载恢复，实验也不会因此自动继续。没有环境变量、命令行override、定时解锁或自动恢复接口；未来解除必须有单独明确授权及人工审阅的配置变更。

新增`software_benchmark_shared_server_hold_v057`在以下实际资源入口的第一步检查：

- 新NAT registry启动。
- v057评分容器的create和start。
- 环境准入的execute、run_one和worker。
- 16个原候选补评的prepare、run和run_one，以及评分器score_request。
- 新v057模型host runner及controller主入口。

配置缺失、JSON无效、版本不符、自动释放标志不符，或缺少明确释放授权的`hold=false`，均按暂停处理。异常在读取任务配置、创建输出目录或调用进程／容器之前返回，避免产生新的半启动任务。

只读状态、只读准入验证与owned cleanup入口保留，不受该暂停阻断。宿主挂载恢复操作没有接入此项目实验开关；事故恢复仍由根代理按其授权范围单独执行。

改动前七个v057源文件的精确字节已归档至[pre-shared-server-hold-r1](../../artifacts/software-benchmark-v057/revisions/pre-shared-server-hold-r1/index.json)，保留此前CPU／准入证据。旧v056源码、候选、评分和主机恢复文件均未修改。

两项必要纯CPU检查通过：12个实际资源入口都在任何外部进程／Docker调用及新输出目录创建之前被阻断；配置缺失、无效或未经授权的释放声明仍保持暂停。Ruff通过。未启动NAT、容器、模型或评分。

验证结果见[validation.json](../../artifacts/software-benchmark-v057/shared-server-hold-r1/validation.json)。该历史验证及其配置哈希保持原样；当时配置的精确字节另存于[修订前档案](../../artifacts/software-benchmark-v057/revisions/pre-hold-seal-r1/index.json)。当前仅更新原因文字，说明已确认挂载可见性恢复，但事故期间工作负载影响及独立安全准入仍未核验完毕；`hold=true`、`release_authorization=null`、`automatic_release=false`和阻断语义均未改变。

新的[执行策略](../../config/v057-native-execution-policy.json)和[执行绑定](../../artifacts/software-benchmark-v057/execution-repair-r1/binding.json)已封存本模块、当前暂停配置以及实际host runner／controller的来源。此轮只做一次纯CPU来源绑定一致性检查，见[封存结果](../../artifacts/software-benchmark-v057/shared-server-hold-seal-r1/validation.json)；没有重跑既有控制，没有启动资源。挂载可见性恢复和绑定一致都不代表实验已获准恢复。
