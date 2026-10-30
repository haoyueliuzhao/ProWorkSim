# v096 原首次调用接续准备：按用户要求封存，未启动

用户要求先封存余下异常、汇总现有结果后，本轮停止继续开发和验证。79 项准备工作状态为 `user_requested_archive`，没有启动正式模型调用、API 请求、生成／评分容器或 GPU；不能将方案准备或 CPU 控制算作新增实验结果。Qwen 保持此前暂停状态。

## 已准备范围

原面板中 78 项已核实三张请求账表均无调用，另有 1 项原先未开始、现有环境控制已经合格的任务，共 79 项（REF 38、PROJECT 41）。准备的物理索引为 6090–6168，逻辑任务身份、原题、seed、思考模式和每题 500 万输入加输出 token 上限不变。这些属于原面板尚未发生的首次模型调用，不是 79 次新增采样；实际调用仍为零。人民币总限额仍为 1700 元，旧费用及未知预约没有退款或释放。

已经生成题单、配置、执行计划和未部署源码，并在独立归档中保留精确源文件字节及 SHA256。归档包括通过显式入口和 Python 依赖关系收集的 398 个文件；其中大量为原有依赖，并非本轮新增或修改。生产授权文件、生产源码封存索引、协调器服务规格、启动意图、启动回执及正式任务资源 claims 均未生成。

## 实际完成的 CPU 检查

| 检查 | 已观察结果 | 边界 |
| --- | --- | --- |
| 早版真实初始化和 REF／PROJECT FIFO 桥 | 通过 | 使用脚本化响应和临时账本，没有真实 API；随后源码还有修改，不能替代最终版本整合验证 |
| 最终独立评分子进程请求验证 | 通过 | 两接口实际 `validate_request`，并拒绝外来身份和被修改的依赖清单；未执行正式评分或创建容器 |
| 身份、三账表零请求及权限边界单测 | 15 项通过 | 已完成测试的结果；用户要求封存后没有追加测试 |
| 定向 Ruff | 通过 | 仅已完成的检查结果 |
| 最终组合控制 r2 | 未完成 | 测试审计钩误将 `subprocess.DEVNULL` 打开的 `/dev/null` 视作禁止写入，冷清单子进程启动前退出；按用户要求没有继续修复或重跑 |

因此，当前准备版本不能标记为整体验证通过或可直接启动。失败的是 CPU 检查器自身的文件写入限制；没有因此消耗正式模型预算，也没有正式运行结果。

## 资源与后续边界

本子任务未创建或启动服务。此前由主代理创建的空 `parent096` 资源组由主代理按空组释放规则收尾，本报告不代替其清理回执。归档不授予运行权限，不写入 approved AUTH。以后若用户要求继续，仍需审阅当前源码、完成尚缺的整合控制并复核原身份及剩余预算；不能自动接入已有模型调用的其他历史异常。

证据入口为 [封存摘要](../../artifacts/software-benchmark-v096/user-requested-archive-r1/summary.json)、[CPU 状态](../../artifacts/software-benchmark-v096/user-requested-archive-r1/CPU-validation-state.json)、[源码索引](../../artifacts/software-benchmark-v096/user-requested-archive-r1/source-index.json)、[计划索引](../../artifacts/software-benchmark-v096/user-requested-archive-r1/plan-file-index.json)及[归档方案状态](../../artifacts/software-benchmark-v096/user-requested-archive-r1/archived-runtime-proposal-state.json)。这些是准备与封存证据，不计入实验正确率或技术未知评分结果。
