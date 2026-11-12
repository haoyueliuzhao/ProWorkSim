# 同12逻辑回合的零API部署恢复

r1队列已经关闭并清理，但首两回合在actor创建参数阶段因named volume前缀不匹配而失败。r1资源分配器生成 `pws-v203-2-1-...`，实际沿用的v066 container_options只接受 `pws-v066-...`。两个volume都已removed，actor/controller未进入正常求解；唯一账本requests表0行、实际API费用0。旧结果及source seal保持，不能把这两项部署故障报告为模型失败或新增模型尝试。

r2新增独立scope/episode/prepare/seal源文件。新BATCH为 `runs/software-benchmark-v203-2-1/passive-pilot12-r2`，新user unit为 `proworksim-v203-2-1-passive-r2.service`。物理slot_index2032200–2032211、首波2032200/2032201；12条任务、seed、逻辑slot_id、condition、组织、实际模型工具/提示/摘要/通信、controller与SDK均原样复用。现有SDK bundle-r2不重新打包。ledger.sqlite与cash-before.json仍指r1唯一150元账本，新增现金0、新增逻辑模型尝试0。

实际资源分配器恢复v066兼容前缀，name内仍使用新BATCH绝对路径与新resource key的SHA，因此不是复用旧Docker对象；既有provider的ownership/claim SHA、卷类型、actor读写/controller只读、CPU/RAM、network none、cap_drop ALL等验证不放宽。新pair12、volume12；代码/交付评分最多各12。只有Requests2317/Pylint4661需要4个新gold/empty控制，其他10题由新grader证明task/image/dataset/官方评分语义等严格一致后显式复用r1实际控制证据，不能只按passed标志准入。

Requests2317仅私有评分器可使用NET_ADMIN/NET_BIND_SERVICE，httpbin.org与www.google.co.uk两个逻辑Host均映射127.0.0.1，不使用外网、host network或宿主port/bind。第二Host按主协调任务明确授权加入；此前未执行的冷准备和execution-plan.json保留。当前规范计划为 **execution-plan-r2.json**，SHA `961cb6934ae624f3bbcda42956e650a423d3b1f956e6b03e096ff202ed66e968`；新冷评分目录grading-r2、grading-coordinator-r2。新增appdirs离线wheel只用于Pylint4661评分环境，不进入模型提示或工具。评分侧实际是否qualified须以主任务后续真实控制结果为准，本记录不提前声称通过。

两项必要CPU控制通过（2 passed in0.44s）：第一项检查12条新旧logical IDs/seed/config模型字段精确相同、同账本、实际episode私有scope/bundle/closure与128GiB门绑定；第二项在临时资源目录实际执行原生claim_resource，随后将其产生的真实格式volume name送入volume_options/validate_volume及actor/controller两套container_options/validate_container，验证完整参数链路。原错误前缀被明确拒绝作为回归控制；没有消耗正式资源身份，没有Docker或API调用。证据cpu-controls.json，复算tests/test_passive_deployment_v203_2_1_r2.py。此前只检查provider参数而未将实际allocator名字串联的覆盖缺口在此补上。

r1首两条team_admissions为closed但没有requests。主任务的新activation处理必须在0request与旧清理证据下将两条旧未付费operational admission转入新增审计表，再解除这两条准入状态；原requests/费用/旧结果不能重写。这是同逻辑回合的首次模型准入恢复，不是新增预算或重采已有模型轨迹。本子任务只读审阅并给出绑定/一致性约束，没有修改账本。

新封存入口为 `tools/seal_passive_pilot_v203_2_1_r2.py`，source快照目标source-snapshot-r2。它引用当前新scope路径，保留已冻结bundle/controller/runtime_inputs，纳入新host/队列/activation/analyzer、grader/environment源、4个control request、10份严格资格、cold scorer/reuse decisions，以及环境JSON递归声明的wheel/certificate引用、appdirs wheel及来源文件。是否实际执行seal/启动由主协调任务完成，本子任务没有启动Docker/API/service。
