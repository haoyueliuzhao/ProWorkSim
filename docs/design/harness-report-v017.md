# H1 v0.17 只读比较与组合选择

`python -m scripts.harness_report_v017`读取原launch、冻结protocol、各窗口summary/progress、实际episode/rollout/runtime、owner身份和评价guard。不运行模型、SQL、隐藏评价器或优化器，不重算奖励，不从旧H0/S1填补结果。

```bash
PYTHONPATH=src .venv/bin/python -m scripts.harness_report_v017 \
  --protocol qwen35-9b=examples/harness-v17/h1-plan/h1-qwen35-9b.json \
  --protocol qwen38-27b=examples/harness-v17/h1-plan/h1-qwen38-27b.json \
  --output runs/harness-v017-h1-report-NEW
```

默认run为 `runs/harness-v017-h1-{candidate}`，launch为 `runs/v017-launch/h1-{candidate}.launch.json`；可用重复的 `--run candidate=path`、`--launch candidate=path`覆盖。未启动时声明protocol用于保留48个计划槽；实际launch后的protocol除 `launch_gate` 准入元数据外须与声明一致。输出必须是新目录，包含 `report.json`、`report.md`、`selection.json`。选择文件引用完整报告的路径和SHA，实际选择对象包含candidate、harness、run_root、protocol_ref、真实初始actor身份和排名依据，供H2及四项目运行绑定。

## 分母与缺失

四组合各保留12槽、完整case/fact/repeat及岗位预算。区分closed_known、closed_unknown、open、interrupted_open、not_started；未知不补0。只要完整分母仍有缺失，整臂原均值、完成率和完整配对均差即为null；观测到的已知奖励和完整责任数另列，不能冒充全批结果。

每个模型按6情境×2重复匹配SDK和native。原均值任务权重是实现/复核各1/3，pair/chain各1/6；另报四任务等权宏均值。情境是主要事实分母，不把48例当作48个独立项目，不用H1均分减S1均分。同种子不代表生成文本相同。

## 冻结选择规则

严格使用builder的 `SELECTION`，不新增业务成功率阈值、不优先SDK。全部两模型实际launcher结束后才能输出最终选择。每个组合须有12例已知、实际记录有效且原episode与rollout绑定、评价guard成立、实际actor身份维持同一fresh初态、零更新、源不变及实际分配成本。未知/未启动或缺失证据的组合不进入自动H2选择，原分母与已测成本仍保留。

合格组合依次按完整实现+复核数（8槽）、完整pair+chain数（4槽）、本臂分配设备秒、candidate/harness字典序排序。没有合格组合时输出 `no_eligible_combination`。`selected`是相对开发初始化选择，不是基础能力充分的认证。

本臂设备秒为其实际slot结束−开始秒数之和×该模型声明且launch实际分配的设备数。整进程含加载、准备与检查点的总分配设备秒仅在模型层列一次；剩余过程成本不强行平摊，也不在两臂重复计算。此值是分配设备时间，不是GPU kernel活跃时间。

## 行为断点

只读提取首次实际sql_build的位置、角色剩余决策额度、执行状态，以及既有独立评价保存的正确build证据。成功执行不等于内容正确；没有独立保存证据时不补判。submit尝试、正确固定提交、复核与staff_done分别报告。最早正确构建及原因无法由现有证据确定时保留未知。

provider义务从**实际选择后的model request**中解析公开conditions，记录当时可见的请求/工作ID及随后选择的动作，不将“看见”推断为“理解”。世界拒绝及SQL执行错误分别寻找同角色下一真实request，并在owner记录存在时核到原生消息与渲染提示；只报告是否包含原错误及后续显式同work_id动作，不仅凭工具名宣称恢复成功。

work_note、work_todo、history search/read按实际模型call统计机会与原始token成本；缺失token保持未知，另列已测部分。一次work_replace_text对应的world write回执不会再计为第二个模型动作。笔记是否改善后续决策、检索是否因遗忘发生以及失败原因均不由此推断。

## 控制与使用边界

4项人工夹具覆盖冻结排序及并列、未知不填0、源guard、两进程未结束不得选择、48槽中未来槽保留、共享加载成本不重复、真实请求错误对齐、正确build/submit/done区分和缺失token不补0。测试通过（0.22秒），Ruff通过。夹具不是模型结果。

实际并行运行已读取两次中间快照：均保留48槽并拒绝提前选择；第二次已有9B首槽闭合、记录与raw episode/身份链接一致，其他槽继续保持原状态。快照读取不是全局原子操作；运行中不同文件可能对应邻近时刻，应以最终进程结束后的新报告作最终选择。

第三次中间读取发现报告器把普通工具的list型result误当object，因而未生成报告；它没有影响模型任务或奖励。已在报告器按实际返回类型区分，并将此正常工具返回加入现有行为控制。失败说明留在 `runs/harness-v017-report-third-error.json`。
