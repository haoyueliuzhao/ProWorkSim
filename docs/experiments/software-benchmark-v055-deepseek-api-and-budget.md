# v055 DeepSeek Flash 官方直连与费用约束

本模块为新增强模型对照提供独立 API 和费用账本，不修改 v054 的模型、推理进程、冻结文件或已运行任务。六条件的 12 次真实中性接口准入已通过；下述准入与成本不是正式 500 题完成率，正式结果由独立队列报告给出。

## 2026-10-21 官方资料核对

- [人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)的实时页面列出 `deepseek-flash` 对应 `DeepSeek-V4.1-Flash-1017`。旧 `deepseek-v4-flash` 只是兼容别名，不用于本次实验。输入缓存未命中／命中、输出的高峰单价分别为每百万 token 2／0.04／8 元；空闲时段减半。模型上下文 1M，最大输出 384K。
- [2026-10-17 更新说明](https://api-docs.deepseek.com/zh-cn/news/news261017/)明确 API 已更新到 1017 版本。模型别名没有不可变的版本承诺；记录响应 `model` 和 `system_fingerprint`，不声称具备本地权重 SHA 那样的固定身份。
- [思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)要求显式 `thinking.type=enabled/disabled`。默认思考强度是 `high`；思考模式的 temperature 不生效，因此不得把发送此参数称为完成温度匹配。Flash 非思考模式的 top_p 固定为 1。思考模式携带 tools 时，应将所有历史 assistant 的 `reasoning_content` 原样回传；不把它压成普通回答内容。
- [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)规定 `max_tokens` 同时限制完整生成，最大 393216；usage 的 `completion_tokens_details.reasoning_tokens` 是 completion 的子项，不额外相加。`prompt_tokens` 为缓存 hit 与 miss 之和。接口适配按完整 usage 核算实际 token。
- [并发限制](https://api-docs.deepseek.com/zh-cn/quick_start/rate_limit/)给出 Flash 每账号 2500 个在途请求，非按 API key 独立计算。超过会返回 429；本模块单实验默认上限 64，不把官方极限直接设为本机容器并发。官方可能先发送空行保活，客户端支持此格式，但仍有请求时间上限。
- [token 计算说明](https://api-docs.deepseek.com/zh-cn/quick_start/token_usage/)指出实际量以 API usage 为准。字符换算不作为精确计量或人民币硬预算证明。
- [余额](https://api-docs.deepseek.com/api/get-user-balance/)与 [模型列表](https://api-docs.deepseek.com/api/list-models/)仅作不生成模型 token 的预检。余额变化可能包含同账号其他调用，不能替代本实验逐请求账本。

## 网络和工具边界

`software_benchmark_deepseek_api_v055.py` 使用 Python 标准库 TLS 连接固定的 `api.deepseek.com:443`。不读取代理环境变量，不创建本地反向代理，不跟随 HTTP 重定向，不调用 SDK 的默认重试。正式生成仅允许 `POST /chat/completions`；免费检查仅允许 `GET /models`、`GET /user/balance`。

请求仅接受文本消息和事前列出的本地 function 工具，不接受 server tool、Search/Fetch endpoint、远程图片 URL、上传文件或任意额外参数。官方刚开放 Search/Fetch，并说明部分 Harness 存在服务端搜索调用；因此本实验不使用该 Harness 的搜索集成。代码树内搜索仍是合法本地操作。Agent 运行环境还需由独立网络策略阻断出网，不能仅靠 system 提示声明“不要搜索”。API key 只在可信控制器内读取，不交给 Actor。

每个任务与条件组合使用固定的匿名 `user_id`，同一回合内保持不变，组间隔离 KVCache。官方 Chat Completions 文档没有可用的 `seed` 参数，本模块拒绝发送未声明字段，不声称原预定 seed 能控制远端采样。Anthropic 兼容文档未承诺 `/messages/count_tokens` 可用或免费，因此不将该接口当作已经取得的精确计量证据。

## 2000 元硬上限的实现

所有预检生成、正式回合和异常尝试共用同一个 SQLite 账本。`BEGIN IMMEDIATE` 将请求编号去重、并发检查和费用预约放在同一事务中。费用以整数纳元存储，避免多进程浮点累积误差。已出现的请求编号永不自动重放。

每次发送前，以官方上下文 1M 对应的 1048576 个输入 token 全缓存未命中，加上该请求明确的输出上限，按高峰单价预约。虽然这是较宽的输入预约，它不依赖未验证的本地 tokenizer 或字符估计。成功取得 usage 后，按真实 hit、miss 和完整 completion 结算并释放差额。每个典型 2048／32768 输出请求临时占用约 2.114／2.359 元额度；这不是请求实际预计费用。

初始 r1 设计一律按高峰价格结算；在首个付费请求前，r2 修订为：预约仍全额高峰价，仅当预约至响应结算的整个 UTC 区间，向前后各扩展 300 秒后，均不与工作日 UTC 01:00–04:00 或 06:00–10:00 高峰窗口相交，才按半价结算。不推断法定节假日优惠；跨高峰、无时区、时间倒退、无法判定的时间或超过七天的区间均用高峰价。以此在保守边界下使用官方空闲时段折扣，而不改变模型设置。

逐请求记录 `tariff_basis_json`、高峰等价费用和实际采用的保守费用。`settled_upper_cny` 与 `committed_upper_cny` 仍是费用上界，不是供应商账单；`settled_peak_equivalent_cny` 保留已结算请求全按峰价计量的可比值，`peak_equivalent_cny` 还包含尚未明确的全额预约。硬上限的有效性依赖已冻结官方价格没有上调；长时间运行需外部核对价格变化，不能声称协议可以控制供应商未来改价。

连接中断、HTTP 错误、缺失或不自洽的 usage 均保留完整预约，不把失败返回擅自视为免费。没有 TTL 自动释放。已失去进程的在途记录仍持有额度；这会保守降低可用预算，需通过另存的供应商证据处理，不能原地删除历史。额度不足时只禁止新请求；已完成生成的 CPU 测试、补丁锁定和评分可继续。

若 API 返回的 output 使用超过请求上限，账本全局 halt；当前异常预约保留。入账拒绝后不自动重试，也不把系统故障记成模型修复失败。所有实际 token、缓存、模型与指纹仍可从请求记录核对。

r2 初始增加共享服务故障停发：401／402／403 首次发生立即停发，其余连续三次系统故障也停发。此策略在正式回合前被用户“异常不得阻塞队列，最后统一处理”的补充授权修订为 r3，原准备记录和费用不改。

r3 对单次 400、429、5xx、传输或协议异常保留未知预约及异常记录，继续其他任务；连续三次后，仅对新请求设置 30 秒冷却，进一步连续故障将冷却增至 60／120／240／300 秒，最长 300 秒。冷却不是对原请求重试。每个异常请求身份仍只进入一次，未发出的新请求等待冷却结束及原任务软期限。成功结算清零连续计数和冷却。在途回合与官方评分继续，异常集合末尾另行处理。

401／402／403 及既有用量越界、账本完整性门仍会硬停止新 API 请求，避免共同账户故障产生大量不明费用。硬停发不取消在途，也不解除费用上限；在途成功结算仍不会解除已经触发的硬停发。

## 最小必要控制

新增测试覆盖：8 个进程竞争单一 2000 元硬上限；缓存命中及思考 token 子项只计一次；超时预约不释放且同 request_id 不能重放；拒绝搜索 server tool 和远程非文本内容；代理环境不改变固定官方 host，302 不重定向；供应商 output 越界全局停发。

第一次控制在 Python 3.14 的默认 forkserver 建 Unix socket 时被当前 sandbox 拒绝，五项其余控制通过。改为本机支持的显式 fork 后，六项全部通过，1.03 秒；新增模块及测试 Ruff 通过。两次均为纯 CPU 程序夹具，模型请求 0、计费 token 0。未对已有 v054 全库重复测试。

r2 仅执行七项针对新增价格边界和共享故障的控制，0.15 秒全部通过：包含两段峰窗、300 秒边界保护、周末、跨日、未知／倒退时钟、峰价预约后闲时结算、高峰等价值、三类账户错误立即停发、400／429／5xx／传输错误的混合连续计数、成功清零及在途成功不解除全局停发。未重复此前已通过的全套控制；仍为 0 模型请求、0 计费 token。

r3 仅执行一项对应的新冷却控制，0.13 秒通过：混合失败触发有限退避、无在途时仍禁止新请求并不给它登记已派发、到期后恢复新身份请求、原失败不重放、成功清冷却、所有未知预约继续计入预算。模型、请求 payload、采样、工具、历史、计量、价目、人民币 2000 上限和正常成功结算路径均不变；只增加正常成功结算时清除可能存在的冷却元数据。因此已通过的 12 次真实中性准入不重复运行。共享账本须留存旧策略及费用证据后做明确的策略版本迁移，不能另建空账本而遗漏已消费费用。

## 免费官方预检

2026-10-21 23:39 CST 首次在工具 sandbox 内查询因 DNS `gaierror` 未建立连接，保留 `runs/software-benchmark-v055/metadata-preflight-r1.json`。随后按已授权的直连网络在 sandbox 外执行一次双端点预检，`metadata-preflight-r2.json` 同时记录 `/models` 与 `/user/balance` 成功：`deepseek-flash` 可用，CNY 余额满足本轮 2000 元上限。公开记录仅保留 `sufficient_for_2000=true`，具体余额仅本地留存。没有模型生成或付费 token。查询只为认证读取密钥，没有输出或提交密钥；余额充足不是六组实验的完成保证，也不能把其他账号调用扣费计入本实验。

## 官方离线计量准备

采用 [DeepSeek 官方 recipe](https://github.com/deepseek-ai/deepseek-recipe) 的 0.2.0 稳定版（2026-10-20 发布），通过清华 PyPI 镜像直连下载 CPU wheel，逐字节校验 PyPI 官方 SHA256 `259812bf382bc82668b672707c5922095cc4f5f60a6c514ff89640bb62a746f7`。以独立 overlay 加载，不安装进既有本地模型或 SDK 环境。wheel 为 cp310-abi3，适用于 Python 3.10 及以上。

仅从 DeepSeek 官方 ModelScope 仓库下载 1017 的 tokenizer、配置与许可，仓库文件 revision `9f9818127fdfbb60feba204799d617a874b32a86`，tokenizer SHA256 `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b`。本轮全部资产新下载 19,215,853 字节，模型权重下载 0。Hugging Face 元数据直连未成功，因此同时保留其已查得 revision 身份，不冒称已独立证明跨站文件字节相同。

新计量器调用官方 `ChatCompletionRequest.convert` 和 `DeepseekV41Encoding.encode`，完整处理工具与思考历史，并使用 recipe 的特殊 token 分段规则，避免把用户文字中的控制符当作真实控制 token。recipe 0.2.0 只接受规范模型名 `DeepSeek-V4.1-Flash`；本地计量时显式映射 API 别名，实际请求仍发送 `deepseek-flash`，其他内容不变。

输出同时保留原始本地 token 数和事前固定的 128 token 工程余量，不把本地统计声称为供应商精确 usage。模型真实 usage 仍为计费与实际消耗依据；已完成中性 API 控制核对两者偏差，不能在正式回合越界后静默改余量。原生完整 schema 不再采用“UTF-8 字节数等于 token 数”而造成过度初态拒绝。

思考／非思考、无工具／有工具历史四个纯 CPU 形态已成功计量，原始 token 数分别为 49／369／23／338，加固定余量后为 177／497／151／466。初次模型别名不被 recipe 接受、一次 system Python 缺 openpyxl 的启动失败均保留为准备故障；改用明确的规范模型映射及已有项目 Python 环境。未产生模型推理或费用。

## 真实中性准入与共享费用留存

六条件各按事前方案执行两次真实 API 请求，共 12 次，全部通过工具连续性、思考历史回传和工程 token 预留核对。累计 **90,131 个输入加输出 token**，按符合闲时保护条件的费率结算保守费用 **0.05128168 元**，对应峰价等价值 **0.10256336 元**。这一费用已计入全轮 2000 元预算；没有额外的准备预算，也没有因策略升级另起空账本。

| 中性准入条件 | 请求 | 输入 token | 输出 token（含思考） | 其中思考 token | 保守结算费用／元 |
|---|---:|---:|---:|---:|---:|
| REF 非思考 | 2 | 15,102 | 118 | 0 | 0.00829848 |
| REF 思考 | 2 | 15,149 | 122 | 0 | 0.00836148 |
| MATCH 非思考 | 2 | 15,102 | 119 | 0 | 0.00830248 |
| MATCH 思考 | 2 | 15,150 | 126 | 4 | 0.00837848 |
| PROJECT 非思考 | 2 | 14,377 | 134 | 0 | 0.00889188 |
| PROJECT 思考 | 2 | 14,486 | 146 | 57 | 0.00904888 |
| 合计 | 12 | 89,366 | 765 | 61 | 0.05128168 |

官方 usage 的输入数与本地 recipe 原始计数存在实际差异：REF／MATCH 的两轮均为 −14，PROJECT 的两轮均为 +56。所有这 12 个输入都落在事前冻结的 `local_count + 128` 预约内。因此可以说明这批中性形态的工程余量足够，不能据此声称公开 recipe 与供应商 tokenizer 严格相同，或任意更长任务历史都已被证明安全。部分启用思考的短中性调用报告思考 token 为 0；表中如实保留，不以非零思考长度作为模式是否启用的替代判据。

2026-10-22 00:16:06 CST 已在唯一的 `runs/software-benchmark-v055/budget-r1/ledger.sqlite3` 上完成明确的 r2→r3 策略迁移。目录名 `budget-r1` 是账本实例身份，账本内部策略版本为 r3，两者不是两个独立预算。迁移前后 12 行请求记录的 SHA256 同为 `923a9e6a18c71c7bd9d969559893c3e93c101591db16a9609d8247e89bfd124c`，原 token、费用、请求身份和完整结算均保持，没有重放、删除未知预约或解除硬停发。此时准备结束的预算剩余为 1999.94871832 元；这是本实验授权额度余额，不是供应商账户余额。

旧账本策略 SHA256 为 `f5135579cf960c3d5cc387fba196a8e17662bf47f3e5d4d01a2f4e35274832c8`，新策略 SHA256 为 `6b5d03cb68577e0d2cd0e33f2ed84ea57c2ebe2b2704f84e422d4f6542632aca`（均包含 max_concurrency=64）。正常模型 payload、工具、采样、计量、价目和总额上限没有变化，故不重复真实准入。

## 小型证据归档

[API 与预算归档](../../artifacts/software-benchmark-v055/api-budget-r1/archive-index.json)保留 r1／r2／r3 CPU 控制历史摘要、原先已执行的冷却等待控制记录、r2→r3 迁移收据与旧新策略、12 次真实准备调用的使用量和费用摘要。CPU 历史摘要明确标为既有工具结果的事后整理，归档阶段没有重跑测试、调用模型或再查 metadata。

[tokenizer 归档](../../artifacts/software-benchmark-v055/tokenizer-r1/archive-index.json)保留准备 manifest、官方版本与 SHA 选择记录、国内下载及完整性回执、CPU 计量结果和准备故障说明。两组共 21 个小文件、74,273 字节，不复制 wheel、tokenizer 大文件、模型权重或 SQLite 数据库。

公开 metadata 仅保留模型列表、文档声明版本与服务端可观察名称／上下文，以及 `sufficient_for_2000=true`。服务端 `/models` 的名称是 `DeepSeek-V4.1-Flash`，没有可独立固定到 1017 权重的 SHA；与官方文档的 1017 声明分列。确切供应商余额、API key 和原始认证资料不公开归档。
