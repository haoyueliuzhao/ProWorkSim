# 原Requests回合首次模型续接叶队列

该队列只承接原12题中Requests2317这一条尚未调用模型的逻辑身份，slot_id仍为 `v203.2.1:psf__requests-2317:DEEPSEEK_NT_REVIEW2_V141_B5000K:202611122032107`，seed与两名固定成员、5M团队限制原样。新物理index2032307、BATCH `passive-requests-leaf-r3`，不替换题、不增加逻辑模型尝试、不重采已付费轨迹，也不改父r2队列或服务。

仍使用r1原150元唯一ledger.sqlite与原cash-before/原API POLICY。叶队列初始化只要求本slot请求0且没有既有admission、没有本slot活跃父资源或本leaf已消费生成身份，不拒绝其他原题已有的合法付费请求。实际现金准入继续使用原SQLite事务里的整队最坏40元预约；没有新账本、新150元或预算转移。资源并发MAX_GENERATIONS1和全批API max_concurrency8明确分开，避免将其他在途题的HTTP误当成本leaf的单队容量。

新普通用户协调unit为 `proworksim-v203-2-1-requests-leaf.service`，MemoryMax8GiB/High7GiB、4CPU64–67，使用--collect，不创建系统slice，不修改已有服务、user manager或linger。actor64–67、controller68–69；两者与父0–63互斥，协调器在自己的actor CPU集合内共享。评分仅在pair彻底清理后用64–67，最多一个grader；容器上限actor1+controller1+code grader1+可能delivery grader1=4，卷1，控制0。自身最大56GiB，和父最坏456GiB合计512GiB；准入额外保留host64GiB（MemAvailable≥576GiB），disk≥128+父32+自身4=164GiB，CPU池至少70。

新scope/episode/hostAPI/prepare文件都是独立源；实际controller、runtime、成员schema、条件、提示、权限、通信、摘要及已冻结SDK bundle-r2保持。volume沿已修复的v066兼容前缀，其name包含独立BATCH和resource key哈希。episode实际私有namespace绑定新leaf，保留原closure和candidate/delivery身份校验。生成与评分在本leaf资源锁下互斥，不能同时占用同一CPU集合。

父r2工程门和已完成CA资格是共同必要条件。启动waiter允许等待门，不预先调用API或创建actor；真实v066 generation entry/actor/controller/volume与API request均要通过两门。父门未出现时gate_status短路返回parent_engineering_pending，其中CA_qualified=False表示此入口尚未进一步评估，不覆盖独立CA真实已通过事实。父门失败或父队列已关闭且无通过门时保持明确not_started/held；不绕过。原slot0请求约束仅用于首次初始化与准入，不能在每次后续API请求都要求0。

新leaf grader已完成严格资格复用：原CA scorer实际重新验证其gold/empty、清理、CA前后证据，再比较task/image/dataset/原baseline/public task/公开入口与官方runtime语义。整个CA环境manifest仅允许新scope归属字段不同；0新controls、1份显式复用资格。代码和交付端点保留原固定member_001及v175同树复用规则，不以passed标志替代原件证明。详见 `../leaf-grading-r3/summary.json`。

我方4项必要CPU控制已通过，前三项一次执行3 passed in0.33s，新增实际host初始化绑定单独1 passed in0.24s，没有重复旧大套件。覆盖原单逻辑身份、实际episode/scope/SDK、共享账本有其他paid仍可准入、own request/admission拒绝、父与CA双门、pair与grader不重叠、actual Host.initialize_for_run只调用leaf guard且HTTP permits=8。测试只用临时数据库、假provider key/transport及内存gate替身，无真实API、Docker、服务或原账本写入；证据scope-api-episode-cpu-controls.json。

规范plan为 `runs/software-benchmark-v203-2-1/passive-requests-leaf-r3/execution-plan.json`，SHA `5712e3c223574d8adb092cc3fadcdb1ced09bd8bcaf79eb220f9911220875a67`。主任务另完成coordinator、launcher和sealer，实际启动状态应读取其新unit与waiting-status/execution/result，不能凭本准备报告宣称第12题已经运行或完成。
