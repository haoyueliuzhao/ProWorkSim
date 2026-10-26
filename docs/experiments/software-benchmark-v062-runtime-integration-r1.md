# v062 原生 BASE/FIX 私有运行时集成

日期：2026-10-26。本记录仅说明代码、普通用户文件打包与 CPU 控制，不表示已获准或已经启动 Docker、模型服务、GPU、任务生成或官方评分。

## 新文件与明确执行分流

新增 `software_benchmark_docker_actor_v062.py`、`software_benchmark_episode_v062.py`、`software_benchmark_sdk_bundle_v062.py`、`tools/run_native_worker_docker_v062.py` 与 `tools/run_ref_controller_v062.py`。这些文件从已验证 v061 对应路径派生，使用独立 v062 policy、资源名、槽位与输出目录；未修改冻结的 v056/v057/v061 文件，也不通过 monkeypatch 旧模块全局常量改变其行为。

BASE5M 使用冻结 v054 `build_llm`、`build_isolated_agent` 和原生 Conversation 组合，原题单独进入初始用户消息；不注入 FIX 公开环境说明、解释器初始化或反馈投影，不启用 v062 stuck/finish 继续协议。

FIX5M/FIX10M 使用 `software_benchmark_native_control_v062.create_conversation`、v057 reasoning 字段投影与持续故障保护、公共初始说明及同一累计预算内的执行协议。固定公开上下文、初始解释器检查和 terminal 反馈说明由公开上下文模块提供；两 FIX 条件使用相同修复。具体提示和次数上限由 native-control 协议独立冻结，不在本文件中另造一套任务专属规则。

## 宿主、actor 与 controller 信息边界

宿主 episode 验证每行 `configuration` 引用的是新派生 host config，内部 `configuration` 才是原固定数值 condition。校验新的 slot ID、slot index、seed、execution arm、source slot ID、replicate、任务和预算完全对应计划行。生成候选锁使用新的 slot ID；旧 slot ID 仅为来源关系，不作为恢复授权。无旧 interrupted-slot replay、旧候选补评或旧 unknown 回填语义。

宿主可读取既有映射以构造公开镜像环境，并保存公开上下文的来源引用。送入 controller 的 task 严格投影为 `instance_id`、`repo`、`base_commit`、`problem_statement`。FIX controller 只收到 `visible_text`、`visible_facts`、版本及初始化所需的公开解释器环境；注册表、baseline mapping 正文、整个 panel、宿主来源路径、哈希列表、参考补丁、评分配置和模型 key 均不传入。

controller 的 config 采用明确字段集合，拒绝未知顶层字段和额外公开 task 字段。BASE config 出现 FIX context 或公开环境初始化配置时明确拒绝。实际模型 key 仍只在可信宿主 HTTP bridge；私有 controller 通过 FIFO 与 Docker stdio 接口传输计量/生成请求，模型请求不从 actor 发起。

## 容器与资源边界

三组 actor 一律 `network_mode=none`、`cap_drop=[ALL]`、无 added capabilities、非 privileged、`no-new-privileges`，不因 Requests 题目扩大网络范围。它们使用新计划中的精确 named volume；actor `/testbed` 可写、controller 同一个目录只读。不新增宿主 bind mount、设备、GPU、端口映射、共享 PID namespace 或宿主网络配置。

创建前先消费精确资源 claim，随后核对 claim 中的新 slot、任务和诊断身份。只清理本轮对应不可变 image/name/label 归属的对象；创建结果未明或工作树留存未完成时，不把资源当作已安全删除。已有固定 CPU slice、内存、PID 上限、容器内部生命周期与宿主只管本对容器的 watchdog 继续保留。

所有运行入口经过新 `require_v062_allowed`，普通文件打包不能自行解除共享服务器 hold。源文件中存在未来 Docker API 调用不等于已执行这些操作。本次集成 CPU 控制没有调用这些入口。

## 原始反馈、投影与异常审计

FIX 使用 NativeToolRPC 子类，先由冻结父类保存原始 request/response，再把原始记录写入独立 JSONL，最后返回仅追加固定说明的副本。模型可见投影另存 `public-feedback-projections.jsonl`。原始 `observation`、原命令和错误标志不覆盖；没有命令重写、自动拆分、自动重试或新的不受管 shell。

执行协议事件逐条写入 `execution-policy-events.jsonl` 并 flush/fsync。即使 `run_controlled_conversation` 因预算、时限或其它异常未返回完整结果，已发送的 stuck 纠正和 finish 自查消息仍可从持久事件中计数；controller 的 finally 另保存全部事件与按 `policy_message_sent` 计算的实际次数。已准备但尚未实际发送的消息与已发送消息分列，不能混记。

原始 RPC transcript、正常关闭状态、累计账本、模型 bridge 状态与 writer quiescence 都保留。可信 `closed` 的 `failure_scope=local`。另有明确的独立任务失败分支：controller 与全部传输可信闭合、累计实际用量完整且无 inflight、唯一终态已归档、writer 与 cleanup 可信静止且本对对象完整回收后，候选内容引发的 `ValueError/UnicodeError` 导出拒绝以专门 `TaskCandidateExportFailure` 保留，标记为 local，使其它任务可继续；该未评分终态不会自动成为候选锁。此分类按发生阶段、异常类型和结构化证据判定，不按错误文字猜测。磁盘 I/O、来源、权限、隔离、响应投影、未知账本、创建归属不明及其他未充分归因的技术未知保持 global 并停止新增派发。普通测试失败、依赖报错或工具格式拒绝可以作为会话内正常反馈继续，不因此伪装为测试通过。

## 诊断与候选锁

计划包含 BASE/FIX 两种零模型部署控制。为保留准备失败后的独立修订空间，资源清单可预留 1—4 号诊断资源；每号对应的 arm 与 task 只从精确 `plan.resources` 读取，不根据数字奇偶猜测，也不自动执行备用诊断。

每个诊断构造真实生产 Conversation 并初始化五工具 schema，经过原生 terminal、file_editor 与 task_tracker RPC，确认 controller 只读视图看到 actor 的临时写入，然后清理临时文件并确认原生关闭。FIX 另通过同一个 terminal 做真实公开解释器初始化，并提交一条明确的合成多命令拒绝输入，要求原拒绝保持且新增说明出现。诊断不运行模型或仓库测试。结束后基线与终态公共源树必须一致，最终 `passed` 还要求可信关闭和 quiescence。

正式生成只在 controller 与 actor writer 都停止后获取唯一终态树，生成 UTF-8 patch 并验证 round trip，再落新 slot 的 candidate lock；评分只能发生在这之后。宿主复用 `software_benchmark_snapshot_recovery_v061.export_utf8_patch` 的纯导出函数，该模块不进入运行时包，也不会执行其中旧历史恢复入口或常量绑定。异常中间树仅保留诊断证据，不自动成为可评分终态候选。

## 最小私有 SDK 包

旧 v061 bundle 会复制整个 `src/proworksim`。新 v062 改为 20 个明确的 native/transport/storage 模块白名单，加一个最小私有 package initializer。新 initializer 仅保留版本标记，不泛导入原项目 World、业务 evaluation、训练或评分模块；这是明确的打包层变化，原项目 `__init__.py` 未修改。

白名单保留冻结的 native worker preload、v054 原生工厂、原始数值/计量逻辑、v057 reasoning/执行辅助和 v062 协议、FIFO、预算与公开 context。各被复制源码均按原字节核对；第三方 SDK 从已安装本地依赖复制，SDK 保持 1.49.6。不下载软件包，不复制权重、官方评分模块、gold 或宿主 key 文件。actor 在工具执行前仍移除自己的私有 SDK/项目文件副本；controller 的私有程序通过隔离边界保留。

为了构造 CPU 工厂控制，仅复用历史 worker-ready 中的公开 `vision_enabled` 与 `tool_definitions`，其来源引用存于可信打包 manifest；其余历史任务与环境数据不进入这个 fixture，也不进入运行时 archive。

## 已执行的必要控制

1. 新边界测试文件 `tests/test_software_benchmark_runtime_v062.py` 首次 10 项通过，0.17 秒。覆盖 BASE/FIX 最小输入投影、隐藏 canary 不泄露、BASE 拒绝修复配置、派生槽位身份、诊断按资源选择、原始 RPC 与投影分离、网络/权限配置和准备失败归属。
2. 后续增加持久事件审计与最小打包白名单后，只针对受影响的 feedback、异常分类及新增白名单控制运行 3 项，全部通过，0.13 秒；另 8 项未重复。再增加可证明局部导出失败分支后，只运行该新增控制，1 项通过，0.14 秒；同时覆盖不确定用量、无终态、非内容故障和创建归属未知的拒绝。该文件最终有 12 个不同测试用例，累计执行 14 次。针对新文件的 Ruff 通过。
3. 首次实际最小包 CPU 控制成功。它导入新 controller、worker 和 FIFO bridge 入口，完成原生 worker preload，分别构造冻结 v054 参考工厂、BASE 生产工厂与 FIX 生产工厂，在合成 workspace 中发送一条合成消息以初始化接口，但不调用 `Conversation.run` 或任何工具。BASE 完整 interface manifest 与参考工厂一致，包括五工具 schema、静态系统模板、压缩器配置和 executor 类；FIX 五工具 schema 与 BASE 一致。BASE adapter 保持原始对象，FIX adapter 使用 v057 guard。
4. CPU audit hook 记录 network/GPU/weights/model/tools 五项全为零。没有启动 Docker、模型服务、GPU worker、任务生成、仓库测试或官方评分。

完整本地凭据位于 `runs/software-benchmark-v062/sdk-bundle-r1/manifest.json`、`probe-source.py`、`probe-stdout.txt` 和 `probe-stderr.txt`。archive 为 150,081,460 字节，SHA-256 为 `ddb11f3a9bfd170300e3fccfd12844af62b74a7a0324a2158f938b3c34ce8f38`，含 14,745 个文件；其主体是本地 Python/SDK 依赖，项目模块为上述 20 项。

这些结果证明的是有限 CPU 范围内的打包与接口接线。实际 Docker 隔离、初始化后的 Python 路径、Requests 行为、真实模型累计预算和能力结果仍需独立已授权运行中的证据，不能由本次导入控制推断。FIX 的新说明、真实准备 action、reasoning 投影和继续协议均改变执行条件；后续成绩不能标作未经修改的原生 OpenHands 官方分数。
