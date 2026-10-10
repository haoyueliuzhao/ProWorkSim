# v0.43 冻结首块启动记录

北京时间`2026-10-10T12:11:48.588973+08:00`，已从独立冻结工作树`runs/v043-frozen-source`启动持久finisher/supervisor，PID `1431208`。执行提交`87301b9871460ffdc85948d8ab1ebfca68506fe8`，计划SHA`99a5bf9b60bafa4c9d3a965f55273d9b7612039209c8afaa02b8834c88bbb0fb`；运行目录`runs/software-organization-v043`，自动报告提交/推送开启。

记录此快照时监督状态为`running`，catalog首块worker状态`running`，物理GPU为`3`。进程启动/模型加载不等于已获得模型输出，真实调用和结果以后续episode原件为准。显存须满足旧阈值并稳定60秒；只允许GPU3/4/5/7。

首块`block-r1-s0`包含PT→SB→ST→PB四槽，先手与A诊断归属均member_001。剩余12槽仍由独立首块机制门约束；仅余量低于1024不停止，但真实反馈硬context阻塞、页面/权限/身份/记录问题或证据不足会阻止未开始槽。无热改、自动重采、额外模型资格题或旧队列后继。

新分层准入和必要9项控制均通过，原v042三份资格false保持；当前模型可见Γ、3072页长、工具/角色说明/runtime仍为原v042。原9B完整common 3/3，actor/critic与反向更新禁用。单槽共享128决定/attempt、500000token、32测试。全库存16是有条件上限，不是已完成数量。

[协议](software-organization-v043-protocol.md)、[准备记录](software-organization-v043-preparation.md)、[启动机器快照](software-organization-v043-launch.json)提供授权、源码、准入和资源边界。终态以后续真实模型报告为准。
