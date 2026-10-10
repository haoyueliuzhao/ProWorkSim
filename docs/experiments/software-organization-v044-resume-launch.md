# v0.44 原十二槽接续启动记录

北京时间 `2026-10-10T16:03:59.548182+08:00`，finisher/supervisor从独立冻结工作树 `runs/v044-resume-frozen-source` 启动，PID `1735073`。实际执行冻结提交 `67a4da1194cdad7de66d7621bf568261338f4f01`，源码树仍为原v044的47eb019…；模型可见Γ、common、原槽身份与预算不变。

本启动快照已分配原3个未启动块：block-r0-s0→物理GPU3，block-r0-s1→GPU4，block-r1-s1→GPU5。已满足原60秒显存稳定检查，当前正加载原common，尚无闭合新槽；加载不是模型输出或正式结果。GPU7保留为空闲备选，最多3resident，不扩大12槽库存。

原四槽位于原根 `runs/software-organization-v044`，不重跑不写回。新目录 `runs/software-organization-v044-resume`，新计划SHA `3a5825cfae7f061a94457b5542772cd7b21e4e69b00e8a3278a69bbae0abb275`，日志 `runs/software-organization-v044-resume-finish.log`。启动前合并验证是唯一16槽、原4已知/新12未开始、原成本1892846 token只计一次。

修订的首块机制门已通过，旧false保留；新3块直接接续，不再选一个首块。每槽闭合后只检查机械/记录/呈现条件，正常R0、自退役和预算终止不阻断。真故障或测量未决暂停未开槽，在途episode结束后不再开新槽，不热改重采。

原12槽最多6000000新增实际token，旧剩余预算不转移；原16总实际上界7892846。新增actor/critic/反向0，旧训练/Contribution/正式更新/确认/缓存生产继续暂停。终态自动报告、提交推送，无自动追加实验。

[接续协议](software-organization-v044-resume-protocol.md)、[准备记录](software-organization-v044-resume-preparation.md)、[机器启动快照](software-organization-v044-resume-launch.json)。
