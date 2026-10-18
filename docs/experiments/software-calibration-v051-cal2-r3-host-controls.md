# CAL2 r3 七条原库存宿主控制

`scripts/software_calibration_v051_cal2_resume_r3.py`仅准备固定新根`runs/software-calibration-v051-cal2-r3`。必须先绑定r2正式`paused/ended`、无活动worker、源环境故障pause、独立环境审计和r1+r2唯一18槽阶段报告。只接受原r2同时满足`not_started`及`attempts=[]`的七槽：parse-2/U，以及xmltodict两题的原六个条件。按原18库存顺序保留seed、状态、先手及预算。r2原八条已进入槽全部排除；不存在r2曾有的零生成R例外，任何已尝试的槽都不能进入r3。

新范围为2条R和5条P/U，上限3,500,000生成token、896决定/attempt、160次项目公共测试。仍为原18432/2048、Γ1、原actor、600秒生成声明、6000秒episode硬界，GPU0—7、最多4驻留、原容量共享门。没有参数更新、反向、HOLD或旧余额转移。

原worker代码对象保持不变，监督器AST仅替换一次启动模块字符串，私有命名空间只重绑定VERSION和frozen。旧main-source引用按其SHA匹配r2或r1冻结snapshot，不使用修复后的main替代旧原件。相对r2，新src只允许已单独控制的repo_tests文件改变；旧base宿主须同字节。root另写r3 release/compound并直接绑定新runner源码、类型修复控制、独立环境审计和本宿主控制后，才能提交、freeze和派发。

原boltons环境失败由独立报告overlay处理：原raw分数和runner记录保留，受影响的严格code/Q未知；boltons2U未提交的R_joint=0事实保留。本宿主不删除失败测试、不重评分、不补采旧轨迹，也不声称已证明所有潜在环境行为有效。root选用的r1+r2合并阶段报告是唯一继承费用来源；初始r1报告只作谱系引用，不再次相加。r3账本只记新工作。

三项新增纯CPU控制一次通过（0.09秒）：精确七槽选择与预算；非终态/活动/已尝试/已进入槽拒绝，旧R也无例外；双历史snapshot绑定及正确新worker模块。原宿主、来源、SDK和分词控制均未重跑，Ruff通过。随后在prepare-only部分绑定报告agent确认的终态报告schema，并明确单一已合并费用来源；已通过的三项选择/绑定函数未改变，未重跑测试，最终Ruff通过。摘要为`artifacts/software-calibration-v051/cal2-resume-r3-controls.json`。本次未运行prepare、freeze、模型、GPU、真实仓库测试、SDK或tokenizer。
