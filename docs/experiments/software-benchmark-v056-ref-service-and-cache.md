# v056 REF 驻留与环境缓存接入

2026-10-24。组件服务于固定50题×四档预算的新实验。旧v054/v055科学记录、缓存回收墓碑和运行队列保持；本说明不宣称模型已正式启动或任何新成绩。

## 驻留接口

`software_benchmark_ref_service_v056.create_service_spec(directory, gpu_index, gpu_uuid, port)` 使用关键字参数，返回独立 `spec.json` 的路径/SHA引用。目录必须在 `runs/software-benchmark-v056` 下；每次实际模型启动使用全新目录，不允许在已有ready/identity/key/launch身份上原地重启。

启动：

```bash
.venv/bin/python tools/serve_ref_budget_v056.py --spec <spec.json> --sha256 <SHA256>
```

建议由独立systemd用户service管理，`KillMode=control-group`并给正常关闭不少于60秒；该工具只停止自己创建的进程组，服务之外其他使用者不在清理范围。

引擎复用原始Qwen3.5-9B检查点和原vLLM0.32.0环境：BF16、单卡、131072窗口、prefix caching关闭、max_num_seqs=1、qwen3 reasoning/qwen3_coder工具解析、原模型服务名。采样、每题预算和模型调用额度由冻结controller负责，驻留不修改它们。新部署只参数化GPU、loopback端口和输出目录。

保留原真实REF容量资格receipt和模型manifest身份，另外绑定vLLM安装METADATA及实际启动脚本。启动前两次核实同一物理UUID、A80080GB、空闲至少66560MiB；没有空卡或util=0要求。复用原全项目GPU UUID／最大8驻留租约，再取得独立端口锁并检查端口未占用。忙或容量不够返回75，没有占位显存分配。

API key每resident新建0600文件，仅作为可信controller路径提供，不把值放入argv或ready记录。引擎只监听127.0.0.1，显式离线并清除代理。旧环境Python symlink在host上可能显示不存在，它指向私有sysroot的Python3.12；实际启动继续经`run_ref_preparation_v054.sh`，不因此重新安装运行库。

`ready.json`提供`identity`引用、`identity_value`、`endpoint`、`api_key_file`、`gpu_index`、`gpu_uuid`、`host_process`和`resident_child_pid`。identity保留原适配器要求的model_revision/vllm_version/raw_release/adapter_sha256/model_manifest_sha256/context_limit/max_output_tokens/service_admission_complete；容量证据明确继承旧资格，HTTP readiness不是新模型生成控制。

驻留一直保活，回合结束不会卸载。控制器需要核对ready宿主身份及未出现closed.json，并为每个resident最多调度一题。服务器退出写closed.json；独立宿主仍须取得cgroup静止证据，不能单凭“已发送停止信号”宣称GPU完全释放。

## 新缓存代次

科学计划为`artifacts/software-benchmark-v056/plan.json`。共享模板使用其精确`cache_root`：`runs/software-benchmark-v054/v056-budget-cache-r1`。采用此独立目录以复用原已验证UID、只读镜像导出和初始化helper，不改旧native-lazy-cache及其墓碑。v056正式Actor的目标目录由新v056 helper管理。

单题入口：

```bash
.venv/bin/python tools/prepare_ref_budget_cache_v056.py \
  --plan artifacts/software-benchmark-v056/plan.json --plan-sha256 <SHA256> \
  --instance-id <固定题单ID> --active-reserved-bytes <其它活动任务峰值预约>
```

省略ID并传`--max-tasks 2`只准备固定题序前两题；后续队列应按题序显式传ID，最多ahead2题。`--status-only`只返回已有状态。状态包括qualified/pending/resource_wait/failed/preparing_or_interrupted/evicted；单题失败保留failure.json，不自动重试已进入初始化，不更换任务。bootstrap循环在一题失败后继续其余预选题。

每次准备从已固定baseline_mapping对应本地Actor镜像导出，进行零模型真实公开解释器/版本/初始树/用户身份检查，不运行基准测试或隐藏评分。输出引用是原`lazy-preparation.json`四项环境资格，外加v056的plan、mapping、路径和metadata stat绑定。旧qualified记录不能代替新payload存在；新payload后来被回收时状态返回evicted，不冒称ready。

状态目录为`runs/software-benchmark-v056/cache-preparation-r1/<ID>`，包含started/qualified/failure；`active-reservation.json`公开活跃准备进程身份和128GiB保守峰值预约。最多一个准备worker，按`free−其它活动预约−128GiB≥128GiB`准入。队列须将此活跃预约纳入后续派发计算，并提供其活动生成/评分的剩余预约；这不是对共享文件系统的硬配额。缓存回收只能在同题四档均终态、相关进程和锁静止之后执行，不能清除实验记录、候选和评分。

## 必要验证与首次准备

驻留六项CPU控制覆盖：数值设置不随端口变动、共享卡容量与UUID检查、占用端口不误接入且释放锁、容量不足零分配、旧身份不可重启、端口失败释放GPU租约。缓存三项控制覆盖缺payload不假ready、空间不足不建立任务准备意图、题单外任务拒绝。共九项通过，定向Ruff通过；这些控制未加载模型。

已启动一次零GPU bootstrap unit `proworksim-v056-cache-bootstrap-r1.service`，按冻结顺序准备pylint4970、sphinx7889，使用4CPU/24GiB宿主边界。此处记录派发事实；具体成功／失败以新缓存逐题回执为准。


## 四档闭合后的自动模板回收

队列提供不可变终态快照，调用同一CLI加`--reclaim --state <snapshot.json> --state-sha256 <SHA> --instance-id <ID>`。快照必须绑定原plan，且包含该题四个确切条件；不能仅凭已出现四行计数放行。

回收前要求四档生成均closed/deferred且quiescent、原result证明资源slice已释放且无cleanup错误；评分均official_report/deferred/not_applicable，已有评分worker需明确静止。相关outer worker必须按PID/start_ticks确认已退出，actor/controller cgroup现场必须空或已消失。持preparer排他锁与原cache任务锁，检查实际新代次rootfs身份、无挂载、固定manifest匹配，再仅删除rootfs。资格、manifest、初始化记录和所有实验／候选／评分保留，写独立tombstone。旧cache不在允许路径。

缺记录、进程活跃、锁忙、半途删除意图等情况一律返回deferred，队列可继续其他任务；本工具不停止那些进程，也不为凑齐清理资格伪造静止记录。完成的回收可幂等读回原receipt，但半途intent需要独立核对。

新增三项回收CPU控制已通过，缓存控制共六项；连同驻留六项共十二项定向控制。未通过测试触发实际删除。首两题pylint4970和sphinx7889现均已qualified，真实公开初始化后各自临时clone已清理；正式四档仍由队列独立决定派发。

四个首批模型服务已按root授权启动，GPU0/1/2/4、端口18056/18057/18058/18060，unit名`proworksim-v056-ref-gpu<idx>-r1.service`，由systemd用户管理器管理，CPUQuota1200%、MemoryMax96G、Restart=no、KillMode=control-group、TimeoutStopSec60。各目录service-unit.json与service-launch.json保存归属和首次启动回执；具体ready时间以resident ready.json为准。

后续只读确认四个resident均已生成认证ready，GPU0/1/2/4各实际驻留63,249MiB、余17,903MiB；本组件没有正式任务派发或模型生成请求。小型启动与首两题资格汇总见`artifacts/software-benchmark-v056/ref-service-cache-admission-r1.json`。该观察不替代root对新controller/预算账本的必要准入。


## 真实SDK构造补充

新控制`tools/check_ref_budget_sdk_v056.py`复用已合格v056 Actor机制，另建独立克隆和可信SDK控制器，只构造BudgetRefAdapter、GuardedRefAdapter、真实LLM、五工具Agent与Conversation512，并执行其真实延迟初始化。不发送问题、不运行会话，HTTP/count/complete被保护性拒绝。

首轮SDK已能实际构造，但比较器把旧合成manifest中的file_editor工作目录与正式/testbed逐字比较，产生false；这一个目录字段差异已从worker原件确认，其余三工具schema一致。原失败和零用量保留，比较器仅按正式工作目录绑定该字段，独立r2通过全部五工具逐字段比较、LLM输入98304/输出32768、思考与seed、10M账本/512attempt/decision和Conversation实际512限制。两轮HTTP/count/complete/model/token/正式claim均0；未因该比较误报修改生产推理、工具或预算。

r2 RPC关闭、作用域静止、克隆回收及资源释放通过；小凭据保存在`artifacts/software-benchmark-v056/sdk-construction-control-r2/`。首轮失败克隆另以原已释放slice证明及当前systemd静止观察收尾，原false不改。
