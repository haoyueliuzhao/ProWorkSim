# v117：拒绝历史与公开测试依赖修复

本次仅实现并做 CPU 控制，未调用真实模型/API，未创建容器、监听端口或操作 GPU，也未修改共享服务器配置。旧 v110–v116 源码、账单、补丁与评分保持冻结；这里的“通过”均指实现控制，不代表新的基准成绩。

## 1. 非法工具参数不再把 REF 历史恢复变成系统异常

原 REF 7244／7251 的模型响应分别包含非法控制字符或未闭合的参数 JSON。OpenHands 正确拒绝了这些动作，生成真实的 `ActionEvent(action=None)` 和 `AgentErrorEvent`；旧适配器随后仍要求历史参数能被普通 JSON 解析，导致下一次请求的历史恢复失败。

v117 的真实 REF controller 明确接入此前 v114 的来源绑定修复：只在原响应、工具 ID、未执行的 SDK 动作和实际错误事件四者一致时，保留 SDK 自己产生的 malformed-call 标记进入后续历史。原模型响应及坏参数字节不变，原费用保留，错误也继续可见。修复不猜测正确参数、不执行被拒绝动作、不自动重试，更不恢复旧已停止实验。

PROJECT 的处理位置不同：它在返回 SDK 响应之前就严格检查 JSON 和公开工具 schema，原格式错误已经有“下一个预算机会可自行纠正”的路径。因此没有强行给 PROJECT 制造 REF 的 SDK 错误标记。新安装函数只核验原结算、零动作执行和实际追加的公开错误反馈，并保存来源回执。两组都使用原会话和原账本；后续纠正仍消耗正常机会与 token。

真实 SDK 控制把原 7251 的截断参数用于一个新的脚本化响应，然后仅返回两次明确结束请求。REF 和 PROJECT 均正常经过拒绝、一次结束自检和最终结束：各 3 请求、3 决策、843 token；PROJECT 三层账单相等，没有世界动作、测试或提交。原坏参数、费用及错误保留，无自动重试。REF 完成分支先通过，随后同一脚本的独立 PROJECT 构造被当时未完成的 cursor 接线检查拒绝；修复该独立接线后只重跑 PROJECT，不重复 REF。PROJECT 的另一项 no-tool 控制由工具修复模块独立完成。

接口：REF 在创建模型适配器时使用 `build_native_llm(..., rejected_history_folder=...)`，在 `bind_ref_conversation` 后调用 `bind_native_history`；PROJECT 在新 worker 构造完成、首个 step 前调用 `bind_project_worker`。这些入口拒绝安装到已消费的回合。[实现](../../src/proworksim/software_benchmark_rejected_history_v117.py)、[真实控制程序](../../tools/check_rejected_history_sdk_v117.py)、[REF 完成证据](../../artifacts/software-benchmark-v117/rejected-history-sdk-r2/REF/completed-control.json)、[PROJECT 控制证据](../../artifacts/software-benchmark-v117/rejected-history-sdk-r3/result.json)。

## 2. Requests2931 的递归 fixture 是公开依赖缺失

实际公开测试使用了正确的 `/testbed`、原 Python 3.9 和 pytest 7.4.4。公开 `requirements.txt` 明确声明 `pytest-httpbin==0.0.7` 和 `httpbin==0.4.0`，公开测试中的 `def httpbin(httpbin)` 则是在包装插件提供的同名父 fixture。这种写法本身合法。旧运行未加载该插件，父 fixture 不存在，pytest 才报告 recursive dependency；不能把这项环境错误直接解释成修复代码错误，也不应让模型通过重写 fixture 掩盖它。

v117 从现有本地、散列已记录的公开 wheel 缓存提取这两个包及其 METADATA 声明的传递依赖，形成独立公开测试依赖层。没有下载、pip 安装、隐藏评分脚本、验收测试、参考补丁、评分 CA 或出网通道；没有复制 `requests`、`pytest`、`_pytest` 或 `sitecustomize`。依赖选择必须与原始公开 baseline 的声明匹配，模型修改 requirements 不会改变已准入依赖。主包的精确版本及完整依赖闭包均受检查；本次实际准备、核查的是 Requests2931，其他任务不能据此自动宣称合格。

原 `public-environment.json`、解释器、工作目录、默认测试命令、模型可选 pytest 路径与过滤规则不变。两组的同一个建议公开测试入口，仅在测试子进程中加入固定依赖层 `PYTHONPATH`；不修改宿主环境。PROJECT 在 PID1 中固定 profile 和执行环境，仍由受管调用执行同版本测试并消耗原测试预算。REF 的原生终端能力保留，launcher 是便利入口，其可修改文件不是不可绕过的权限门，也不会产生 PROJECT 的交付证据。

公开依赖保存于 `/opt/pws-runtime/public-dependencies/v117`，初始化时核验 manifest、每个文件及原公开 requirements/fixture 的身份。本轮真实 pytest `--collect-only` 控制确认插件 entry point 自动加载，并同时找到插件父 fixture 和原形状的本地包装 fixture；没有执行测试体或启动 HTTP 服务。该 CPU 控制使用现有 SDK Python 3.12.3 和缓存 pytest 7.4.4，而非正式容器中的 Python 3.9，因此不能称完整环境资格已通过。最初直接使用宿主 Python 3.14 时旧 Werkzeug 的 `ast.Str` 不兼容、第二次控制缺少 pluggy，两次失败均保留，生产包没有为迁就控制而改版本。

仍有明确边界：原镜像 pytest 7.4.4 保留，没有强行安装公开 requirements 中更早的 pytest 2.8.1；插件自带旧 TLS 证书保持原字节，本次没有证明其 HTTPS 全部可用；未来真实 fixture 只可使用既有私有容器的 loopback，不能启用宿主监听或外网。正式运行前仍需对新公开环境做有限、单独记录的资格检查；目前不把完整 Requests suite 标成已修复通过。

[离线制备实现](../../src/proworksim/software_benchmark_public_dependencies_v117.py)、[公开运行时验证](../../tools/public_test_dependencies_v117.py)、[managed actor 接线](../../src/proworksim/software_benchmark_managed_actor_v117.py)、[native 公开入口](../../tools/public_test_library_v117.py)、[依赖清单](../../artifacts/software-benchmark-v117/public-dependencies-r1/manifest.json)、[实际 collection 控制](../../artifacts/software-benchmark-v117/public-dependency-collection-r3/result.json)。

## 3. 这些修复能支持的结论

CPU 证据支持：已来源绑定的非法模型参数可以继续作为正常拒绝留在原会话中；公开 httpbin 插件可以由既有离线包恢复注册；两个执行条件的建议测试入口可以使用同一依赖层。它们尚不证明正确率提升，也不消除报告中已经看到的语义遗漏、测试不足和完成自检失实。下一次真实运行必须使用新的冻结版本，旧分数与停止事实不回写。
