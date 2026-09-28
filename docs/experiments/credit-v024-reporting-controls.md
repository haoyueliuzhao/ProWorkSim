# v0.24 只读报告器的有限验收

`report_credit_v024.py` 只读取原有 JSON、日志及 SHA 引用；不调用模型、重放世界、重新评分或加载 checkpoint tensor。真实 v0.24 执行前完成以下四项 CPU 测试，运行命令 `.venv/bin/python -m pytest -q tests/test_report_credit_v024.py`，结果 **4 passed in 0.05s**；两文件 Ruff 检查通过。本页不是 v0.24 模型实验成绩。

1. 十二对中七对已知、五个初端点未知且末端点均为零时，差值和 −1 的兼容界为 `[−6/12,−1/12]`，不是未利用末端点信息的宽界；错 checkpoint 身份保留未知，改变同情境业务初态直接拒绝配对。
2. 两臂真实保存的 D0 admission 只在 `reward` 与 `credit` 不同时允许一致性结论；改变一个 loss mask 会得到 false，缺一臂返回 null。运行报告还将与共同 origin 内预声明的投影及两配方 prepare SHA 核对。
3. `+0.2` 事件结算及 `−0.2` 终点补差完整保留并验证总和守恒；擅自把负补差改零会被识别为不守恒。
4. 初评失败、其余阶段未启动且监督器已终止时，报告为 `closed_incomplete`，已失败阶段 45 秒仍计费，主估计保持 null；未终止的监督器只能得到 snapshot。此控制使用明确的人工元数据 fixture，没有模型或实际 GPU 占用。

报告主比较为十二个固定 slot 上的 Handoff-RTG − MC，辅助为两臂分别相对共同 θ0。六情境的两次固定种子重复保持 A、B、维护交错，分结构各四对。每一端点必须通过实际 assessment 文件 SHA、嵌入评价一致性、当前 canonical `preparation.json`、checkpoint 元数据身份/配方、参数与 RNG 状态保护检查；未知和失败不互换。只有完整终端协议及共同起点、实际 D0 比较证据都满足时给出预定主估计。

训练报告分别记录共同采集六条、MC 第二窗六条、RTG 第二窗六条，计十八条新训练经历；共同 D0 被两臂各消费一次，所以最多二十四次 episode 级消费、四次窗口更新。报告不重新生成 prepare 或 reward，而是读取实际 admission、真实账本和 update 中保存的 critic/advantage，核对目标与事件位置算术、优势等于目标减旧 critic，以及最终 checkpoint 步数等于本臂两个完整窗口步数之和。窗口未闭合的保存步数明确只是进度。

入口：

```bash
.venv/bin/python -m scripts.report_credit_v024 \
  --run runs/domain-v024 \
  --output-json docs/experiments/credit-pilot-v024.json \
  --output-md docs/experiments/credit-pilot-v024.md \
  --require-terminal
```

报告输出必须在原始 run 目录之外。终态归档器将调用相同接口；六个阶段的失败、加载及重叠单卡占用均独立计费，预算为内部 36 GPU 小时、外部 0。没有新增恢复阶段。若执行结束但协议不完整，报告保存已有证据与兼容界，不宣布模型仍在运行，也不把部分结果包装成完整方法比较。
