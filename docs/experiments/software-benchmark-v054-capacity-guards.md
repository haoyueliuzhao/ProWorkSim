# v054：容量等待监控器的生命周期与部分计账修复

日期：2026-10-21。本轮只修改容量准备监控器并执行纯 CPU 控制，未加载模型、占用 GPU 或运行任何评测题。REF 65 GiB／MATCH 45 GiB 准入门、原数值配置、REF 98304＋32768／MATCH 16384＋2048 token 窗口、每种模式最多两个合成请求均未改变。

本文保留 guard 修订时的 CPU 控制范围。后续根代理已补充最终配置封存与宿主解释器入口修复，并启动等待监控；当前 seal／服务状态以[模型准备记录](software-benchmark-v054-model-preparation-r1.md)为准，不以本文最后的历史“尚未启动”状态覆盖后续事实。

## 1. 封存与启动

`tools/prepare_model_capacity_v054.py --seal-only --output <目录>` 在最终 owner／runtime 源码固定后创建排他的 `source-seal.json`。其中记录模型来源回执、配置、原生工具接口以及实际服务／生成／资源代码 SHA；不重新散列完整模型权重。已有 seal 不覆盖。

实际监控仅由已登记的 `proworksim-v054-model-capacity-preparation-rN.service` 调用，默认 r1；检查调用进程等于该服务 MainPID，保留 invocation 和 cgroup。普通 CLI 仍可使用 `--inspect-only` 查看容量，但不能直接绕过服务身份开始加载。启动及每次 dispatch 前再次核对源文件与 seal，MATCH 实际 owner contract 也须与封存值相同。

根代理负责在最终源文件固定后建立 seal、启动监控并选择新 attempt。监控服务应提供足够的停止时间，例如 `TimeoutStopSec=120`，让它能等待模型子服务的 30 秒停止限额与实际退出证明。封存不等于 GPU 已可用，也不等于正式实验获准。

## 2. 模型服务自行持有 lease

不同输出目录共用一个监控锁；每个模型服务由独立 host wrapper 持有：

- 固定的 capacity preparation 单 resident 锁；
- 已有 `GpuLease` 的物理 UUID 锁；
- 项目共用的 `resident-slot-0..3` 之一。

父监控只做无 GPU 内存分配的可用性探测，启动前释放探测锁；真实 lease 在模型服务自身保留，避免父子互等同一个 flock。获得全部 lease 后还重新核对该 UUID／index 的实际空闲显存，再执行模型命令。

模型 unit 使用 `BindsTo`＋`After` 指向确切监控 unit。监控 SIGTERM 进入自身清理；监控突然消失时 systemd 依赖负责停止其独立模型服务。每个 unit 仍有 KillMode=control-group、SendSIGKILL 和硬运行期限。清理核对原 invocation，等待外层 launcher 回收，并检查记录的 cgroup 已不存在或 populated=0；不能仅凭 MainPID=0 宣称 GPU 服务已释放。

## 3. 每一次费用都单独落盘

`smoke-ledger.json` 在发送请求前保存完整输入＋最大输出预约。完整响应经过输入计数、输出 ID（MATCH）及 usage 一致性检查后才结算。

若第一个请求成功、第二个请求中断，最终回执仍含第一个请求的 `known_actual_tokens`；`actual_tokens=null`，第二个请求的完整 `unsettled_reserved_tokens` 保留。若失败发生在第二次生成 dispatch 之前，则只有已完成请求的实际费用，不虚构一次未发生的生成。失败不重采，不将未知费用写成 0。原始请求／响应保留，顶层 receipt 无需依靠扫描散落日志才能知道部分成本。

## 4. 本地 REF 服务身份和结论范围

每次 REF 启动生成独立随机 API key，只写入本地 0600 文件。专用启动入口在进入私有 runtime 后将其注入 `VLLM_API_KEY`；密钥值不在公开 argv、请求体或回执中。所有 HTTP 请求均携带 Bearer，包括就绪探测；不会仅凭相同的 model name 和 context window 认定端口属于本次服务。

实际安装的 vLLM 0.32.0 支持 `VLLM_API_KEY`；其默认认证保护 `/v1` 等前缀，`/tokenize` 不在该前缀内。因此 `/v1/models` 和生成请求的认证确认服务身份，而分词请求同样发送认证头；本文不误称官方 middleware 已对每条路径强制认证。没有修改官方 vLLM 代码。

`real_tool_calls_observed` 单独记录 REF API 实际返回的工具调用。MATCH 容量接口直接测原生数值 owner，工具解析观察明确记为未在该端点评估。模型没有按提示发出工具调用不会触发重采，也不会凭容量 smoke 成功就声称完整工具端到端已验证。

## 5. 必要 CPU 控制

仅新增三个不同控制，**3 passed，0.07 秒**；新增文件 Ruff 通过：

1. 封存配置改变、错误 MainPID 和替换后的 monitor invocation 均拒绝。
2. 第二次半途失败保留第一笔 20 个已知 token、第二笔 18432 的预约及未知实际总额；重复 ordinal 拒绝。
3. 用完全合成密钥和替代模块入口验证密钥在私有入口注入环境，未进入 argv；未导入 vLLM 或模型。

这些控制验证新 guard／账本／密钥入口，不宣称 GPU 数值、真实生成或 systemd 模型生命周期已实际运行。本轮没有重跑旧控制或启动监控；最终 source seal 留给根代理在所有相关文件冻结后创建。
