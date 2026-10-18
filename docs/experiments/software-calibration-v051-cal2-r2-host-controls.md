# CAL2 r2 独立续库存宿主与控制

实现为`scripts/software_calibration_v051_cal2_resume.py`，仅准备固定新根`runs/software-calibration-v051-cal2-r2`。原18条库存保留；新根只选择原14条完全未开始槽，以及原boltons-1/R的唯一首次模型暴露例外。原三条已生成P/U轨迹永久排除，不重跑、不补评分。R例外要求原审计充分绑定：112个源码文件原字节相同、已加载raw release、所有prepared/started/complete/fault计数为0、实际call和episode文件为空、无mini账单/轨迹/终态guard，且原报错精确来自初态文本往返绑定。新增排序与CRLF修复不改变原任务字节。任何准备过的native请求或轨迹都会拒绝此例外。

原worker与监督算法通过私有命名空间复用，不修改旧宿主模块或原冻结快照。worker保留同一代码对象；supervise的AST只替换一个worker模块字符串。命名空间另绑定新宿主VERSION与r2的frozen函数；动作、模型、预算、资源、终止和评分逻辑沿原算法。真正派发的模块为`scripts.software_calibration_v051_cal2_resume`，因此子进程检查新15条计划。

prepare必须在提交后执行，并绑定root另写的r2 release/compound。原计划中指向main的历史源码引用按原source_files清单映射至旧snapshot相同SHA，不能把修复后的main误认作旧源码。新src仅允许mini与repo_tests的已披露窄修；shell和其他src保持原字节。compound直接绑定mini/repo_tests/shell当前源码SHA、修复控制与本宿主控制。旧状态、原source-qualified、原报告、原监督器与旧成本来源单独封存引用。

新15槽上限为7,500,000生成token、1,920决定/attempt、9条P/U合288次公共测试。原227,876token/22完整生成及原R加载失败worker成本仅保留在原阶段，最终合并时计一次；旧余额不转移。新驻留全部重新加载actor，不复用原R模型状态。r2仍最多4驻留，GPU0—7按原容量共享门；18432/2048、Γ1、演员身份、600秒生成声明和6000秒episode硬界均未改。r2内原禁止loader后重试规则保持，不能把本次明确的旧R例外扩大成一般失败重排。

只运行3项新增纯CPU控制：固定剩余选择与预算；零暴露R正例及任何生成/轨迹/来源异常反例；旧源码snapshot映射及唯一worker模块替换。3项一次全部通过（0.09秒），原16项宿主控制及来源/SDK/分词资格未重跑。首次Ruff只报告unused import，删除后通过。之后新增的prepare-only单根、旧成本和修复源码引用门经过静态检查，未执行真实prepare/freeze；须由root在独立release/compound和提交完成后运行。控制摘要为`artifacts/software-calibration-v051/cal2-resume-controls.json`。本子任务没有GPU、模型、真实仓库测试、SDK请求、tokenizer调用或HOLD任务内容访问。

root审查另要求把缺席的`resident/calls`或`episode`目录视为合法零material，存在为非目录、符号链接或非空目录则拒绝。只读事实显示原R这两个目录实际均存在且为空；prepare仍补齐合法缺席分支。此修订未改三个已通过控制函数，未重跑测试，仅Ruff复核通过。最终新摘要为`artifacts/software-calibration-v051/cal2-resume-controls-r2.json`，原摘要与匹配SHA的源码副本保留。
