# Qwen REF 生成终止后的 GPU 接力规则

2026-10-22。本修订只改变 GPU7 的资源退出门，不改原始模型、三个实验条件、题单、seed、单题预算、候选导出或评分器。原动态池政策和全部冻结源码保持原字节；独立 overlay 显式覆盖 `ref_to_mp_after_all_500_scored` 这一旧资源门，不能据此改写旧实验结果。

原门要求全部 500 个 REF 回合正常闭合并取得明确官方评分。已有技术未知会让这个门永久不满足，即使 GPU 会话和全部任务进程早已结束。官方评分运行在 CPU 上，也无需占着 REF 推理服务。新门要求原始 1500 槽身份不变、其中 500 个 REF 生成状态全部为 `closed` 或 `technical_unknown`，随后逐项核对原 claim、外层 worker、登记 scope 的静默证据，以及原 GPU7 resident 的精确进程身份、空会话、零在途请求和正常健康状态。任何证据不足都保留失败原因，不自动停止模型或重试任务。

技术未知、未知成本和评分状态全部保留原值；退休证据禁止出现 `all_500_ref_scored` 字段。每次退休绑定不可变队列快照、终态身份摘要、实时静默证明和停止前身份，且停止后须证明原 unit 退出、原 cgroup 为空、原 launcher 消失。只有这一台已核对的 REF resident 会被停止。后续沿用既有 MATCH／PROJECT 部署、容量门、物理 UUID lease 和六请求双会话交错准入，独立记录加载及准备成本。模式切换需要一次 REF→MP 的服务替换，不代表在同一数值后端上直接混跑三组。

注册链继续只追加。新 reader 对原 `dynamic-pool-r4` 精确政策身份启用新退休分支；其他池，尤其 GPU6 的独立 kernel 池，原样调用旧 reader。原注册事件的静态准入、事件连续性、重复 GPU／resident 防护保持。未来原数值 worker 的独立入口先安装 reader，再调用原 runner；现有在途 worker、controller、sentinel、模型 owner 和官方评分无需改变。独立 provisioner 沿用原状态文件及同一锁，保留此前失败设备的不可自动重载记录。

本文件记录实现和控制完成，不单独声称实际服务切换已完成或 GPU7 已接力。正式上线和完成时点以独立部署回执和实际新增任务绑定为准。全部 500 个 REF 生成结束前，新管理器仅检查廉价终态条件，不提前运行逐题进程检查或改变 resident。

## 必要控制

`tools/check_ref_handoff_pool_v054_r1.py` 的八项 CPU 合成控制全部通过：499 正常闭合加 1 技术未知且评分仍待完成的真实语义、拒绝重复退休、拒绝伪造评分完成、拒绝在途请求、拒绝注册链篡改、其他池透传、精确一次停止编排并保留原队列与失败设备、存在待运行 REF 时不探测／不停止模型。停止编排使用 mock；真实模型调用、真实服务变更、正式 claim 和队列写入均为 0。边界模块及队列／worker 接线另有独立控制记录。

- overlay：`runs/software-benchmark-v054/ref-generation-handoff-r1/overlay.json`，SHA256 `a0b5a1e69d1343a2df2247acc208b5e71265dba45f5b80100d8379567dcae3ae`。
- CPU 控制：`runs/software-benchmark-v054/ref-handoff-pool-control-r1/receipt.json`，SHA256 `f4ba144b5adfb1e0386329e0aed7acda0063282989d0b1739e23271f1f6ffcfd`。
- 小证据归档：[`ref-handoff-pool-r1`](../../artifacts/software-benchmark-v054/ref-handoff-pool-r1/archive.json)。未归档真实队列、模型内容或密钥。
