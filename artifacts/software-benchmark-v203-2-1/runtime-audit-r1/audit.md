# v203.2.1 运行入口与本地部署准备

本记录仅涵盖本地源文件审计和新部署配置准备；不表示真实环境已通过、不表示模型已启动。初始审计与部署准备没有调用模型API、Docker或服务，也未读取凭据内容；凭据只定位为项目根目录 `.env`。

新入口 `tools/prepare_passive_execution_v203_2_1.py` 已物化固定12题、10仓的原预留身份，未替换题目。行号2032100–2032111，首两行是正式12题内的工程准入波，不额外生成回合。单队5M、全批60M上界，新独立150元账本路径在 `notes.json`。历史现金不得复用；金额准入只作用于新开团队，已开始团队保留原token/时间边界并如实结算。

新实现保留 v141 REVIEW2 的模型可见条件、工具、提示、摘要、通信、组织和最终 member_001 交付；`condition('REVIEW2')` 已与原实现精确比较。v157/v167/v172 communication runtime 会扩展通信工具，即使C0也不适用于此处；v193 context runtime也不是本轮基线。仅复用v172观测器的被动存储/错误处理修复，不采用其通信runtime。打包从v143继承原actor公测结果兼容性修复。

新 `scope / alignment / runtime_inputs / episode / project_closure / sdk_bundle / controller` 均为独立文件。episode内部实际AST已经绑定新closure，controller中managed与run_fragment/close_runtime指同一新runtime；新closure拒绝旧批次身份，防止重现v146的旧ID导出错误。controller复用v159最终化顺序，在关闭FIFO前保存owner账本，次生错误不能遮蔽主异常。

资源为8生成、2启动、2评分，8核32GiB协调器；每对actor4核16GiB、controller2核32GiB，grader4核16GiB，另各grader宿主进程4GiB。组合预约64核456GiB，保留宿主64GiB内存、128GiB磁盘余量。仅新named volume（actor读写/controller只读）、无新系统slice、无旧rootfs恢复、无主机bind mount。资源名由新批次路径和resource key派生；atomic allocator使用本批资源锁，评分显式缩为2 lane。

12题的全部official image、actor image和原v064配置均存在于v066完整500题计划；本地映射见 `notes.json`。v066主要资格目录有10题历史passed记录，Requests2317/Pylint4661未找到历史资格。以上仅文件事实，没有检查当前镜像存活、环境或评分效果；不把历史passed升级为本轮qualified，不因缺失而换题。公开测试来自原public-test-registry、baseline_mapping和同一公开入口，隐藏材料引用仅留宿主配置。

必要CPU核验规范结果见 `../deployment-bindings-r2/summary.json`（早期r1保留），复算工具 `tools/check_passive_deployment_v203_2_1.py`：12配置实际进入新episode row/config校验、原条件相等、closure实际import正确、48个旧版本身份被拒绝、私有provider创建/校验共享32GiB controller边界。没有运行旧版大测试套件。实际源冻结、独立现金初始化、环境控制、真实API首波工程准入由主协调任务继续执行，不能由此记录推断完成。

评分新适配进一步移除不相关5414的offline provider准备，12题实际provider均为None、额外capability空、两条评分lane及新closure绑定经CPU检查。`tools/seal_passive_pilot_v203_2_1.py --seal`只绑定用户已给的150元及Docker权限，不是申请新许可，也不会启动执行；在并行开发结束后才能运行。其proposal记录每队按最坏5M×8元/M=40元启动预约，以总150元约束和已开始团队不中断共同准入，初始现金实际最多3队并行，资源能力8队不是承诺8队同时付费。

后续协调任务要求只读核对现存Docker磁盘：普通用户通过Unix socket成功GET /info一次，DockerRootDir仍在/data0真实device66306，观察余量约51.70GiB；data1本人目录device66307余约508.22GiB，而/data1/zhuxinrui是回data0的符号链接。未创建、停止或修改Docker对象。sandbox先拒绝socket调用，已授权普通用户escalation后查询成功，无root命令。保持原128GiB计划门不变；另发现旧episode wait_capacity尚有ROOT>=256GiB门，已报告主协调任务，未擅自降低门槛。详细只读回执见storage-readonly.json。
