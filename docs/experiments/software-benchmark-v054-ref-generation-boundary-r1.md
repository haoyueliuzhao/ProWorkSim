# Qwen REF generation 结束边界证据 r1

本修订为 GPU7 完成 REF 后承接 MATCH／PROJECT 提供独立的只读准入证据。它本身不切换驻留器、不发模型请求、不修改任务队列、claim、评分或账单；实际切换由另行冻结的宿主修订负责。旧冻结模块保持不变。

## 允许切换的工作边界

原检查将 REF 的 500 个正式评分全部明确作为转接条件。评分是 CPU 工作，而且已有技术未知必须保留，因此新边界只判断原 REF 生成库存已结束，另以实际 worker、claim cgroup 和驻留器状态证明 GPU 已无旧生成占用。

新纯函数逐项核对冻结的完整 1500 个 slot 字典、顺序、唯一身份及 seed；其中必须恰好包含原 500 个 REF。全部 REF 的 generation 状态只能是 `closed` 或 `technical_unknown` 才具备资格。`pending`、`intent`、`running` 不具备资格；未识别状态直接拒绝。REF 原始 generation 摘要固定在证据中，不按成功率选择，不把技术未知改成正常闭合。

正式评分不作为 GPU 占用依据。证据不会填写 `all_500_ref_scored=true`，不会读取并清零旧的未知 token，也不会触发重跑。MATCH／PROJECT 和正式 CPU 评分可在检查期间继续；末尾只重新比较 REF 的 slot 和 generation 摘要。

## 终态时才执行的实际核查

在所有 REF generation 终态且原驻留器空闲之后，新 collector 才读取 500 个 REF 的小型 claim、scope registry、generation job 凭据。它复用既有 `assert_quiet`、`assert_outer_launcher_exited` 和 `admitted_resident`，检查每一个精确登记 scope 的主进程、调用身份、cgroup 及外层 launcher 已退出，检查 generation worker 已停止，并检查独立 claim 资源 slice 无进程。正式评分 unit 不在检查范围内。

驻留器必须仍是 GPU7 上同一 REF 声明、同一 ready 记录、同一 PID/start ticks、同一 systemd InvocationID 和 cgroup；`active_claim` 为空、`inflight=0`、`poisoned=false`。检查末尾重新读取同一驻留器的只读状态。缺失 scope 或身份不符不能当作通过。

未创建 claim 的异常不会仅凭 `technical_unknown` 获准。该例外要求全部尝试都有精确匹配的 worker exited completion，并有保留的原 result 明确记录 `slot_claimed=false`、`entered=false`、`model_calls=0`；generation worker 必须实际静默，并且不能存在遗留 scope registry。任何已 claim 的回合缺失 claim 都拒绝。

## 必要核验与实际状态

六项 CPU 控制全部通过，覆盖原身份及 seed 变化、活跃状态、未知状态、正常闭合与技术未知混合、CPU 评分继续、未终态时不打开运行期清单、未创建 claim 的严格例外，以及驻留器非空闲拒绝。仅两个新增 Python 文件的 Ruff 检查通过；没有重复整套实验资格测试。

对当时四个 REF `technical_unknown` 进行了窄只读核查。四项均有原 claim 和 scope registry；对应 generation worker、全部登记 scope 和 outer launcher 当时均已退出。这说明这些已有异常不会仅因保留技术未知而永久阻塞新边界。它们的技术未知分类和未知成本保持原样，不据此补记正常完成。

该次状态快照包含 304 个正常生成闭合、4 个技术未知及 192 个待开始；纯资格为 false。未调用完整 500 项运行期 collector，未停止或重载 GPU7。这里的控制结果仅证明新边界规则可执行，不意味着实际切换已经发生，也不是加速效果的观测结果。

实现：`src/proworksim/software_benchmark_ref_terminal_boundary_v054_r1.py`；控制入口：`tools/check_ref_terminal_boundary_v054_r1.py`。小型证据保存于 `artifacts/software-benchmark-v054/ref-terminal-boundary-r1/`，实际切换应另保留终态快照和新运行期凭据。
