# v067 API 准备统计修复

v066 R3 的 API 初始化读取了不存在的 canonical `total_tokens` 字段，因此在调用模型之前停止了 API 队列。该异常未停止 Qwen 或评分。原始 provider usage 有总量字段，但项目规范化后的每次调用只保留 `prompt_tokens` 和 `completion_tokens`；两层 schema 被混用是本次故障原因。

新 `software_benchmark_deepseek_runtime_v067.py` 使用两个明确字段之和校验准备消耗，并拒绝字段缺失、非法计数、重复调用、未知 usage 或与资格总量不符的记录。真实只读账本显示两次调用分别为 340＋45 和 407＋7，共输入 747、输出 52、合计 799 token。没有补填零，也没有重复中性调用。

新模块保留 v064 模型可见协议及已经通过部署验证的 v066 包、DeepSeek Flash 思考配置、原资格、tokenizer、工具 schema、原 slot／seed／配置及唯一 1500 元账本。逻辑 API 身份只写入 `runs/software-benchmark-v067/api-continuation-r1/api-runtime`。原 R3 文件和 provider 暂停记录不改写，不重启 Qwen；旁路 API coordinator 另行绑定。正式初始化及每次派发均要求注入 v067 scoped guard，同时继续通过原 v066 资源授权。未注入新 guard 时在密钥和 client 构造之前拒绝。

验证包括 8 项必要 CPU 测试及 Ruff，均通过。另在正式使用的私有 Python 3.12 下，使用实际旧资格、账本、schema、原 6000 槽计划和续跑 inventory 执行一次完整只读预检查，成功到达 counter／client 构造边界。证据在 `artifacts/software-benchmark-v067/api-preparation-repair-r1/actual-read-only-preflight.json`。

该验证没有读取 API key、创建 client、调用 API、写入旧账本或操作 Docker／GPU。它证明准备路径已修复；真实 API 续跑及后续评分结果须以旁路执行记录为准。

## 独立队列与实际恢复

API协调器现已启动，接续原2968个未消费API身份，保留六组各500题的计划分母和原有结果。最多4个API生成并行，评分异步；持续读取主队列新完成的环境资格，不重复环境控制。它没有Qwen驻留管理能力，启动、关闭均不停止或重新加载Qwen。

新增普通用户协调器限4 CPU／16 GiB，使用原CPU池未使用的164–167号CPU，并先在主队列同一`allocation.lock`下预约。该开销与全部actor、controller、grader、模型驻留一起计入原152 CPU／832 GiB上限；只释放自己的预约。正式任务的容器及评分身份仍取原v066计划，未增开一套API任务或现金预算。

新增8项队列控制和8项资源范围控制通过：覆盖动态资格等待、局部异常、原记录继承、旧身份不重放、禁止Qwen生命周期操作、共享池满额拒绝与自身预约清理。真实[运行快照](../../artifacts/software-benchmark-v067/recovery-live-r1/summary.json)确认Qwen与API均在运行，已出现新的实际API请求和评分产出；快照时为2个Qwen及4个API生成，组合预约72 CPU／384 GiB。后续数字以实时记录为准。

统计由[合并进度脚本](../../tools/report_continuation_progress_v067.py)只取主队列Qwen六组和独立队列DeepSeek六组。主队列保留的API暂停／未开始记录不与实际API续跑重复计入。请求用量继续由原唯一账本计量，完整500题平均值须等该组实际用量齐全才能成立。
