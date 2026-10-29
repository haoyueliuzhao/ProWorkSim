# v094：绑定实际模型线程的授权门

v093 首2项创建环境后，在实际模型线程内被旧授权门拒绝。`host_usage_v066.serve_model_channel` 函数内部局部导入旧v066 guard；仅替换 episode 的 `policy` 不会改变该导入。拒绝发生在函数原 `try` 外，因此线程退出、ready未发出，也没有完整bridge结果回执。此前Docker构造前控制和独立broker授权没有覆盖这条真实线程路径。

## 本轮范围

原44项模型恢复尝试仍未调用API。42项物理6046–6087及其配置原样保留；仅将已创建并清理的6044／6045改为6088／6089，逻辑身份、任务、seed、5M预算与原canonical API registry保持。

v093已实际创建并清理 **4个容器、2个卷**，不能记为零Docker成本。本轮仍最多创建155个容器、44个卷，含先前消耗的累计上限为 **159个容器、46个卷**。新增模型尝试数为0，现金仍共享1700元账本，旧失败及费用全部保留。

新API-only bridge在实际 `episode._run` 所用的 `serve_model_channel` 上显式绑定当前policy guard，不改原模块，不替换全局import。初始化授权、身份或ready异常返回明确的 `ready=false` 结构回执。endpoint、帧顺序、token／调用上限和原计费规则保持；Qwen运行路径不接入。

## 全链检查的范围

| 路径 | 身份与计费边界 |
| --- | --- |
| 实际模型线程→新bridge | 当前44项scope，18219 API broker，逻辑slot身份与原wire版本 |
| `/tokenize`、`/tokenize-prefix` | 原payload、官方counter、未闭合工具前缀校验；不计作模型生成 |
| `/chat/completions` | 原broker authorize→当前scope→逐题累计预算→全局1700元reserve／settle；不自动重试 |
| 响应与持久化 | 原SDK序列化、response normalization、controller response／ledger记录及usage核验 |

另一个 `model_fifo_v064.serve_model_channel` 也有旧guard，但不是当前episode实际导入的入口；新绑定明确拒绝误接该函数。Native stdio的两个转发线程仅校验framing，lifecycle timer仅停止自有对象；这些路径没有另一个旧6000题scope门。

新物理映射及累计成本两项CPU控制通过。最终桥接控制也已通过：从实际运行器 `_run` 使用的最终bridge绑定进入真实named FIFO、原container bridge、SDK消息、官方counter／prefix、原broker、真实1700元客户端的临时账本reserve／settle和controller持久化。REF、PROJECT各保留2条脚本化settled及1条uncertain，费用核对一致；这些是临时CPU夹具数据，未计入实际API账本。最终控制无HTTP／DNS尝试；第一次控制在SDK导入期间触发成本表DNS失败，随后提前设置离线环境与网络审计钩子，失败记录保留，不能把最终零网络尝试扩大解释为所有尝试均未触发DNS。结果见 [最终FIFO控制](../../artifacts/software-benchmark-v094/real-FIFO-control-r1/summary.json)。

已据完整控制封存v094运行源码。CPU控制不访问真实API，不代表远端响应和整套真实系统已验证；本文件不将封存或服务启动等同于恢复实际生成。

上线仍限制预选REF、PROJECT各1项；两项分别出现真实settled付费请求后，才开放48的调度上限。初始项结束却无此证据时保护其余未开始身份。实际并发与配置上限分开报告。

依据：[零模型与已创建环境审计](../../artifacts/software-benchmark-v094/zero-model-environment-handoff-r1/summary.json)。新运行目录：`runs/software-benchmark-v094/physical-startup-recovery-r1/api-coordinator/`。

## 实际启动观察

v094已启动。事前指定的REF与PROJECT均产生了真实API请求与已结算费用，启动门passed=true，随后开放后续原44项派发。记录时活跃任务环境为15，实际生成future为22，在途API请求为1；48是配置上限，不能写成已经48并发。总现金上限仍1700元，原首轮结果和旧未知费用保留。此证据证明两接口真实请求链已进入，不表示44项均已完成或官方评分已通过。

[在线观察](../../artifacts/software-benchmark-v094/live-admission-r1/summary.json)保留时间和实际计费请求身份；当前进度应读取v094路径。Qwen四驻留已在v090按用户要求停止，未恢复。
