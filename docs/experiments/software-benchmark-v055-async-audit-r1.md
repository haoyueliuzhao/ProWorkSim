# 生成与官方评分异步执行的最小审计

2026-10-22的只读审计确认：旧Qwen三组和新DeepSeek六组都已把生成与官方评分拆为独立job、独立systemd worker和独立待办记录。**不会等待某题官方评分结束后才允许其他题生成**。旧队列官方评分并发上限2，新队列上限4；这些是worker上限，不是额外的模型回合数。

旧队列的有效tick来自`software_benchmark_fault_queue_v054.py:380`，先收集回执，再分别调用`dispatch_scores()`和`dispatch_generation()`。`software_benchmark_queue_v054.py:584`按剩余grader容量派发独立score job；`select_pool_slot`依据生成状态与resident空位选择新生成，不要求上一题评分结束。当前恢复及准备优先host沿用这部分逻辑。

新六组的`software_benchmark_queue_v055.py:352`先分别collect generation和scores，生成完成后只将其官方评分请求排为pending。第405行起新生成与待评分各自检查并发容量，分别launch；第185行的launch创建独立`generation-*`或`score-*`目录和unit。启动命令只等待systemd受理，不等待worker中完整实验或评分进程结束。r5仅增加按消费组的环境准备策略，保留这一调度方式。

## 实际同时运行证据

不能仅凭有队列代码便宣称已经并行。此次读取现有worker时间metadata，取得两条直接重叠证据：

- Qwen：PROJECT pylint-4970的官方code评分从09:28:50到09:29:17运行；同时MATCH pylint-4970的生成worker自09:19:27开始且观察时仍running。两者unit和job不同。
- DeepSeek：MATCH-thinking django-11728的官方评分从09:29:56到09:30:26运行；同时PROJECT-nonthinking django-16502的生成worker自09:08:30启动且观察时仍active。两者unit和job不同。

独立job引用、时间回执SHA与systemd状态存入`artifacts/software-benchmark-v055/async-audit-r1/async-audit.json`。09:28:30的九组进度快照恰好处于两边评分队列均已排空的时点（待评分0、active grader0），故不能用该单点的0个评分worker否定此前和随后发生的实际并行。最新进度仅统计code端点；官方worker总数可能包括PROJECT delivery，不应拿worker总数当不同题数。

## 仍会等待的步骤与资源限制

模型主动运行的公开测试与最终官方评分不同。公开测试是该Agent当前工具调用的反馈来源，Agent必须等待结果再决定下一步；它仍是回合内同步操作。v055 PROJECT公开测试有独立clone与进程，并受全局8个许可约束，等待许可／测试执行期间其他回合可以继续生成。REF／MATCH原生终端测试也服从当前工具调用的返回语义。此次没有把未结束的测试结果虚构为已完成反馈，也没有改变单Agent行动顺序。

官方评分只读取生成已经锁定的候选，评分结果不回传模型。它在独立worker内等待CPU测试完成，协调器不被这个等待占住。公共测试、官方grader与生成仍共享CPU、内存和磁盘；资源门、任务环境尚未准备、resident会话满或API预算／限流可能压低并发。当前旧队列等待原因可为共享磁盘峰值预约，新六组也受同一保守预约限制；这属于真实资源准入，不是按题同步等评分。共享完整性异常仍保留停发门，单题技术异常进入延期集合。

没有发现当前调度器把正式评分放回逐题同步阻塞路径。此结论来自最小源码路径与时间回执，不是重新运行测试；没有干预在途任务、读取模型思考或隐藏评分值。约2/4个官方grader的上限并不承诺CPU忙碌时恒定达到该数量。
