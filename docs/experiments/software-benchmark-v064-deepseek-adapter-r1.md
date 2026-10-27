# v064 DeepSeek 思考模式与实际费用计量

本轮只采用 `deepseek-flash` 思考模式，官方当前标注版本为 `DeepSeek-V4.1-Flash-1017`。其公开容量为 1,048,576 上下文、393,216 单次输出；本实验主动限定为与 Qwen 条件一致的 131,072 总上下文、98,304 完整输入、32,768 完整输出。商业 API 别名不等于可核验的固定权重哈希，因此还需保存启动时 `/models` 元数据及各响应的 model／system_fingerprint。[官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

显式设置 `thinking.type=enabled`、`reasoning_effort=high`、`top_p=0.95`。思考模式下不生效的 temperature、penalty 参数不发送；也不伪造 API 不支持的 seed、top_k 等设置。带 tools 的请求必须保留历史所有 assistant 回合的原 reasoning_content，含没有调用工具的回合；缺失不能补造。SDK 投影使用 v057 的真实归一化及不可恢复错误锁，原响应和已结用量保持。[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)

两个接口都使用同一远程计数与生成约定。完整请求由已冻结的官方 recipe/tokenizer 在宿主离线计数并保留原工程余量；它是提交前估计，不冒称服务端 exact token IDs。原生 SDK 还会请求不完整工具回合前缀的计数，这通过独立只读 `/tokenize-prefix` 操作调用官方低层编码器处理，不补造工具反馈，也不将此前缀发送模型。完整生成必须通过正常计数与请求校验。

## 1500 元硬上限

新账本与旧 v055 的 2000 元账本完全分离，不迁移、不重置旧账本。请求先在共享 SQLite 中持久预约，才允许发出 HTTPS；所有正式生成、压缩和中性准备调用共用 1500 元上限。并发门默认 64，且不能超过官方账户级 Flash 2500 并发；实际回合数量仍受服务器 CPU、内存、磁盘及容器限制。[官方并发规则](https://api-docs.deepseek.com/quick_start/rate_limit/)

现金预约保留上一轮已经验证的绝对模型上界：每个在途请求预约 5.24288 元，覆盖完整 provider 容量按峰价计费的保守上界。这个数是现金预留，不是本题已经消耗的费用或 token。保留它的原因是历史上曾观察到提供方输出超过请求 max_tokens；仅按本次 32,768 输出预留无法覆盖这种异常。

使用每百万输入缓存命中 0.04 元、未命中 2 元、完整输出 8 元的峰价。只有请求起止连同两侧各 300 秒保护区确定都在闲时，才按半价结算；不猜测节假日折扣。账本金额是基于 usage 的保守费用估计，不能冒充平台最终账单。[官方计费规则](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

已发送但无可信用量的请求保留全部现金预约，不自动重试；可信 usage 已结算但输出或实际输入超过实验边界时，保存实际费用和 token，隔离该回合，不把无效响应交给模型。元数据身份、用量分区或账目不可信才触发共享止派。只有明确的 `PreDispatchBudgetStopped`／`PreDispatchConcurrencyBusy` 能证明没有发出该次 HTTP；已发送后的异常不能据此退回团队用量预约。

## 计量及覆盖边界

实际 token 总量采用 API `prompt_tokens + completion_tokens`。reasoning_tokens 是 completion 的子集，缓存命中与未命中是 prompt 的分区，均不能额外重复相加。缺失的 reasoning 明细保持未知，不补零。host 按固定 slot/condition 约束每题预算及 512 次调用，controller 保留独立逐次用量和原始响应记录；错误响应的已知费用也进入实际成本。

旧 REF 思考与 PROJECT 思考合计已知用量为 398,517,426 token，已结账本金额 230.03398212 元。将旧条件简单复制三次约为 690.10 元，但旧每题上限只有 50 万，且 PROJECT 的上下文、输出及执行条件不同。这个历史场景不能证明 1500 元足够完成新的 3000 个 API 回合。若货币门先截止，完整计划分母仍为 3000，未开始与用量未知分别保留，不填写为模型失败。

## 隔离与准备状态

API key、现金账本及真实 TLS 客户端只留在可信宿主。无网络的 controller 使用私有 FIFO 与 Docker exec 通道；`127.0.0.1:18219` 只是通道身份，不创建监听端口或 HTTP 反向代理。宿主仅直连官方 HTTPS，禁止代理、重定向和 Search／Fetch API。模型仅有已冻结的本地 function 工具，actor 网络关闭。每题使用独立可取消的 TLS 客户端，共享账本；取消一题不会关闭其他题连接。[官方 Search／Fetch 说明](https://api-docs.deepseek.com/guides/search/)

本文件对应适配、费用与 FIFO 的 CPU 准备，不表示完成真实 API 准入或正式模型运行。官方事实、历史成本场景和必要 CPU 检查见 `artifacts/software-benchmark-v064/deepseek-preparation-r1/`；后续打包及真实通信记录应分别保存，不覆盖准备记录。
