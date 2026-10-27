# v063：v062 单项评分日志编码异常的独立修复

## 问题及测量边界

本修订处理 v062 的 `score-29`：`astropy__astropy-14995`，FIX10M 主测，seed `20261026062090`。该回合已经结束生成并锁定最终候选，原评分记录为 `technical_unknown`，不是模型修复失败。

原候选补丁为 20,173,303 字节，已通过严格 UTF-8 和目标树往返验证。实际异常发生在官方 harness 应用补丁之后、执行评测脚本之前：harness 为记录工作树变化执行 `git -c core.fileMode=false diff`，随后严格按 UTF-8 解码其输出。此次诊断输出在位置 1,067,230 遇到不能按 UTF-8 解码的 `0xe0`，因此提前退出。候选中含有生成的二进制文件；Git 的文本判定不保证输出一定是 UTF-8。

这与 v056 的补丁入口编码异常不同。v063 不重新导出、过滤或改写模型补丁，不删除候选中的测试产物，也不重新运行模型。修复对象仅为评测端的工作树差异诊断日志。旧异常、原候选、原测试结果和本轮正在运行的 v062 源码均保留。

## 修复方案

在新的独立评分进程中，核对已固定的官方函数来源，只替换工作树差异日志的解码步骤。原始差异字节另存并绑定长度和 SHA-256；正常 UTF-8 输出保持原样，非法字节以可辨认的转义形式显示。不得将这种宽容解码扩展到候选补丁、官方测试输出或评分结果解析。

使用新版本、新 run ID 和新输出目录，避免命中旧评分缓存。官方任务、镜像、初始仓库、候选内容、评测脚本及 resolved 判定规则保持。评分结果不会返回模型。修订文件独立于正在运行的 v062；本轮三组及重复诊断继续按原冻结配置运行。

## 实际执行范围与授权边界

独立补评计划只包含本任务的 gold、empty 两项控制及 `score-29` 原候选，共最多三个新容器，串行执行。每个容器 4 CPU、16 GiB 内存，`network=none`、`cap_drop=ALL`、`no-new-privileges`，无宿主绑定、端口、GPU、出网或新数据卷。普通用户评分进程的地址空间上限为 4 GiB，与容器使用相同的四个 CPU；两者内存配置上界合计 20 GiB。只管理本次新建对象，结束后清理。

原 v062 授权按身份和数量限定为 630 个容器，`score-29` 的原评分身份已经消费。因此新增三个评分容器使用独立待授权提案，不能复用旧身份或据此扩大原授权。实际补评须在原 v062 队列完成并确认其资源静止后执行；源码准备与 CPU 检查可以提前完成。

当前文档描述修复和补评准备，不代表已取得新的官方分数。最终是否 resolved 必须以独立补评回执为准。

## 必要验证

诊断日志修复的四项 CPU 回归检查通过（`tests/test_diff_diagnostics_v063.py`，0.15 秒），对应 Ruff 检查通过。检查覆盖原始字节保存、合法 UTF-8 保持、非法字节显示、上游来源与精确修改范围；独立代码审阅确认两处诊断变量不参与 resolved 判定。未重复执行原 v062 的模型或环境资格检查。

固定的官方 `run_evaluation.py` SHA-256 为 `39b7e95f726df65c67f19f8d79a0f5f10f9d9e12e224076c8cb011851d060016`。修复用 AST 构造该函数的私有副本，不改安装目录或上游模块的全局对象。日志中的转义显示不能替代原始二进制差异；精确字节比较应使用另存的 `.bin` 文件。

补评入口另有十项 CPU 检查通过（`tests/test_software_benchmark_rescore_v063.py`，0.12 秒），对应 Ruff 检查通过。覆盖未授权拒绝、其他任务拒绝、三次创建身份不可重用、单并发、清理失败保留占用、父队列仍在运行时拒绝、替换原候选拒绝，以及宿主挂载、网络、GPU、特权等扩展拒绝。独立静态审阅通过。仅执行了本地 `--prepare`，Docker 操作和新模型调用均为零。

具体范围见 [补评提案](../../artifacts/software-benchmark-v063/rescore-authorization-r1/proposal.json)，验证记录见 [scope validation](../../artifacts/software-benchmark-v063/rescore-scope-validation-r1/validation.json)。独立入口为 `tools/run_diagnostic_rescore_v063.py`；只有取得该新增范围的明确授权、原队列完整闭合及两项控制通过后，才允许对原候选补评。

用户于 2026-10-27 明确回复“授权上述限定补评”，授权已单独保存为 [approved-authorization.json](../../artifacts/software-benchmark-v063/rescore-authorization-r1/approved-authorization.json)，现有配置状态为 `approved`。原 `pending` 提案仍保留。授权不改变等待原 v062 队列闭合的条件，也不代表已经执行补评。

## 完成后自动衔接

新增独立普通用户入口 `tools/wait_diagnostic_rescore_v063.py`，原已批准的提案、policy、scorer 和 runner 字节保持。等待进程每 30 秒读取原队列进度，最多等待 24 小时，限 4 GiB 地址空间和原评分通道的四个 CPU。它绑定明确授权、源码、解释器和固定执行命令；只有原队列闭合并通过已有完整准入门，才用同一进程执行补评。撤权、源码变化、取消、原队列停止或已有补评入场记录都会阻止派发，不重启服务或重复评分身份。

等待入口的七项 CPU 状态检查和 Ruff 通过，独立静态审阅通过；未重复先前的十四项检查。启动计划与证据见 [waiter launch plan](../../artifacts/software-benchmark-v063/waiter-launch-r1/launch-plan.json)、[waiter validation](../../artifacts/software-benchmark-v063/waiter-launch-r1/validation.json)。

北京时间 2026-10-27 22:53 已启动等待进程，确认实际 UID/EUID=1021、地址空间上限 4,294,967,296 字节、CPU affinity=16–19，标准错误为空。原实验仍在运行，补评容器创建数为零。此时只是完成自动衔接设置，正式结果仍须等待补评的 `receipt.json`；等待器的 `result.json` 不是评分完成证明。
