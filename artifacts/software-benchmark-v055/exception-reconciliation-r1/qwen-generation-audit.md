# Qwen生成异常的既有证据审计

本次仅审计当前15个generation `technical_unknown`：REF 7、MATCH 4、PROJECT 4。已核对原队列绑定的result／job／completion SHA和claim身份，读取对应小型controller、quiescence及账本摘要；没有扫描rootfs、导出新补丁、运行评分或重跑模型。逐题引用与分类保存在同目录 `qwen-generation-audit.json`。

**基于已有候选锁和评分请求，可直接恢复的结果为0。** 15条均已entered／claimed，均不存在candidates目录、候选锁、官方评分请求，原scores也为空。不能仅因controller曾closed、当前进程已退出或工作区仍被保存，就补写为原正式闭合。

| 类型 | 数量 | 现有证据与处置 |
| --- | ---: | --- |
| 锁候选之前缺少完整静止证明 | 13 | controller已closed、candidate_selected=false；原quiescence均为all_quiet=false。11例model CPU sentinel、2例actor的停止证明记录FileNotFoundError。保留原技术未知；不能用后来的修复或新quiet观察覆盖旧失败。 |
| PROJECT公开工具停止后代超时 | 1 | `sympy__sympy-20801`，controller记录execution_integrity_failure；stderr显示world gateway内停止后代TimeoutError。最终scope静止不等于控制器已经可信闭合；无候选锁。 |
| MATCH控制器读取start.json失败 | 1 | `django__django-15380`，stderr记录JSONDecodeError，未产出controller-result及权威controller用量摘要。claim已进入，不能清除并重跑。 |

13例历史ENOENT与已独立修复的PID退出竞态相容，但原回执没有完整堆栈，不能声称逐例根因均已证明。若后续考虑行政导出，需要另一份独立证据证明原终态工作区未改变、完整writer静止、固定候选语义及原成本完整性；本审计没有获得或伪造这些证明，也没有从残留工作区新选补丁。

用量与生成结果分开处理：15条外层result的model_calls均为null，不当作0。14条保留了controller账本摘要，其中10条native摘要报告完整tokens、4条PROJECT账本报告已扣tokens且无hold；这些摘要合计 **6,378,076 tokens**。这是14条原摘要的可引用小计，不是15条完整成本，也未重新核对全部请求／响应。按原末尾评分器的严格billing规则，完整用量仍有 **2条未知**：`django__django-15380`缺权威controller摘要；`sympy__sympy-20801`虽然保留209257已扣tokens，但controller设置execution_integrity_failure，因此仍不能宣称完整用量已确定。前者未在小计中按零填入，后者的已知摘要保留，未知边界不清除。

本轮新增模型调用、评分调用、GPU探测、原状态／回执修改均为0。原1500回合及每组500题分母保持。
