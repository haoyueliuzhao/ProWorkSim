# v118：PROJECT修复后50题重新评测

用户要求“对project组重新进行实验”。本批重新运行原分层面板的全部50题，仅PROJECT，采用v117受管接口修复、DeepSeek Flash非思考模式，每题最多5,000,000输入＋输出token。每题使用独立初态和新的运行身份；不覆盖旧候选、账本、分数，也不追加REF生成。

## 固定设置与计量

原50题、12个仓库及原问题文本保持，任务顺序不按成绩调整。新物理身份8000–8049，seed从202611040118依原题序递增；API不发送seed，不声称可复现同一生成。上下文131072、输入98304、单次输出32768、512次尝试／决定及原时间上限保持。50题生成总上限250M token，另最多1次PROJECT工具接口中性调用、最多4096 token；它们都是上限，不是预计消耗。

继续原v105累计350元账本。准备时已结算149.10529592元，保留5.24288元未定预约，可用195.65182408元；不增加额度、不删除旧费用。2026-11-04重新核对[官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)，原保守费率仍适用。模型API直连，禁止代理、服务端搜索和网页抓取，密钥仅在宿主受信API进程中使用。

新结果分别统计代码正确率与合法交付率。实际输入、缓存命中／未命中、输出、模型请求数及费用均按本批独立身份统计；摘要计入同一预算，中性准入单列。完整50题均值与已调用子集均值分别给出覆盖分母，技术未知不填成模型失败。旧PROJECT／REF只作历史配对参照，本次不能把多项修复的联合变化解释为单一接口效应，也不称完整500题或独立确认集成绩。

## 环境与运行接线

48题官方评分资格经过本地等价核验可复用，其中Sphinx10614／Pylint6528使用v114实际通过的逐路径测试恢复控制。Requests1766／1921先运行新的4项gold／empty控制；评分保留严格TLS，使用已允许的评分CA兼容层。当前DNS首个公网IP在本次普通用户直连的80／443两个只读GET中均返回200，HTTPS严格校验通过；评分目的地址随后冻结，不自动轮换或重试。

Requests2931的公开pytest-httpbin插件叶证书已于2025年过期。本批另建v118公开fixture profile，只在新测试依赖层更新localhost CA／叶证书与对应记录；v117原件、仓库CA、宿主信任库和官方评分环境不改。新证书含localhost、127.0.0.1、::1 SAN；三个正例、两个负例的真实TLS内存握手通过，没有主机监听。正式模型前，在唯一预定PROJECT零模型诊断中，用原Python3.9／pytest验证私有容器loopback上的HTTP及严格HTTPS。

启动检查还发现并修复两处接线问题：依赖层导出覆盖了父类引用，导致选择性测试继承被跳过；零模型适配器缺少PROJECT身份字段。新v118的真实调用链、选择性测试argv以及完整SDK零模型factory控制均已通过。正式模型可见的工具、历史精简、自检策略继续采用v117；新controller仅补零模型身份与公共环境资格透传。

若2931公共fixture未合格，只将该题列环境未定，其余任务可继续。容器／账单／记录完整性或清理无法证明时才止损；不自动重采已调用回合，不用异常评分阻塞其他独立任务。

## 资源与启动范围

最多16个生成pair、2个评分容器，生成与评分异步；合计最多112 CPU／576 GiB。模型请求并发仍受原账本16上限约束。只创建本批对象，通过已有Docker接口运行`network=none`、`cap_drop=ALL`的隔离容器，无宿主目录绑定、宿主端口、GPU或新系统slice；只有既定Requests评分使用容器内所需私有网络能力。

全批对象上限302个容器、51个专用卷：正式50对生成、1对零模型诊断、50代码评分、最多50独立交付评分，以及最多100个环境控制备用槽。默认只需4项新TLS控制，其他合格控制复用；同一树的交付可复用自身代码评分，不为用满额度而重复执行。结束仅清理本批自建对象。

真实外部评分最多8个TLS session、4096次连接、512MiB载荷，目标仅冻结的httpbin.org地址80／443；两个TLS题串行。2931诊断最多90秒、32次私有loopback连接，与外部评分分开计数。新协调服务为普通用户的`proworksim-v118-project.service`，不重启Docker、修改共享主机挂载／网络／驱动或操作他人任务。

## 已完成准备与复核入口

必要CPU接线、诊断factory、真实evaluator清理路径、冷资格准备、证书及选择性测试控制通过；新离线bundle已加载实际入口，未用CPU控制冒充正式容器资格或模型结果。

- [题单](../../artifacts/software-benchmark-v118/preparation-r1/panel.json)
- [计量口径](../../artifacts/software-benchmark-v118/preparation-r1/metrics-contract.json)
- [完整资源方案](../../artifacts/software-benchmark-v118/runtime-authorization-r1/proposal.json)，SHA256 `8c15a1b177919363a42d4d338014351d239adea7a61cf492064ad0a9d54cb667`
- [生成环境诊断](../../artifacts/software-benchmark-v118/generation-admission-r1/diagnostic-plan.json)
- [评分准备证据](../../artifacts/software-benchmark-v118/grading-transport-control-r1/preparation.json)
- [运行控制](../../artifacts/software-benchmark-v118/runtime-controls-r1/summary.json)

当前运行结果应读取`runs/software-benchmark-v118/project-repaired-r1/api-coordinator/`，汇总入口为`tools/summarize_project_rerun_v118.py`。只有实际产生运行回执后，才能将本方案的准备状态写成已经启动或已经完成。
