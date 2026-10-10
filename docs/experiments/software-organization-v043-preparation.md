# v0.43 准备与分层准入

2026-10-10，依据用户在新审计之后明确要求修订并开展实验，建立独立v043准入与org43模型库存。原v042的P0-A、P0-B/C和代码综合资格三份`passed=false`原件、全部CPU结果及org41/org42未启动状态保持。

## 已完成的必要核验

新准入与调度共9项必要CPU控制通过，静态检查`.venv/bin/python -m ruff check src tests scripts`通过。没有重新分词、重跑旧世界路线、验收、加载模型或反向；新增控制只核验新入口的拒绝/放行和冻结路径。

分层记录见`runs/v043-controls/layered-admission.json`：来源绑定、原代码控制、信息权限、actual selected容量四层均通过；只有原1024-token protected工程余量改为非阻断诊断。没有force开关，不将旧false改成true。

独立复用审查核对67个原资格源绑定和3393个原引用文件、原tokenizer六文件与原生渲染器，以及32历史复制形状+370 SDK阶段的804份selected/protected既有native记录。17份历史测试首页转换保持原Pi040可见范围；36报告211页精确恢复、37报告212个实际呈现片段和470次出现均有原件；两个权限拒绝交叉核验成立。这些仍是旧CPU程序证据，不当作新模型行为。

新入口还从原v040 plan绑定的冻结提交补齐v038/v039 world/runtime/tasks和model_policy共7个不变继承文件的SHA，弥补旧局部source清单的依赖范围。没有改这些文件或模型可见呈现，工作树路径可以变化，实际执行字节必须相同。

原两处历史前缀及28个SDK阶段的低余量位置全部保留，共30处诊断。最小protected硬余量52，原工程超972不能叫硬context超972。请求真正运行的硬门仍是selected+2048≤16384。

## 冻结执行范围

采用原v042分页/世界/context/runtime/反馈测量，不改3072页长、schema、角色说明、briefing、验收或静态删除范围。新driver和输出ID为org43，重新登记从未被模型消费的202610100401/402。原9B完整common 3/3，所有学习计算禁用，新增actor/critic/反向均0。

首块为catalog `block-r1-s0`，顺序PT→SB→ST→PB，member_001先手并拥有初始诊断A。四槽属于总16，不增加模型资格题；其余三个root/seed块共12槽仅在真实机制门通过后释放。不依据R、页数、全读、消息、任务或招募选择；纯工程余量不足记录诊断，真实硬context反馈阻塞或页面/权限/身份/记录问题按协议停止。

单槽共享128决定/attempt、500000实际token、32测试，初始2/活动≤4/累计出生≤6。首块上界200万token，全库存800万token；不是预测成本。只物理GPU3/4/5/7，单任务与资源保护不变，旧训练、Contribution、确认和缓存生产继续暂停。

本准备记录产生时模型阶段尚未启动；实际启动与结果由独立冻结运行记录报告，不从CPU370次响应估计真实模型耗时。源码和资格hash、全部诊断位置、库存、资源界限及日志见[机器记录](software-organization-v043-preparation.json)与[协议](software-organization-v043-protocol.md)。
