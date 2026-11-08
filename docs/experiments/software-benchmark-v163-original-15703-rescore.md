# 15703 原锁定候选独立评分

本次只评分已经存在的15703最终候选，不重跑模型、不重新导出工作树、不挑选其他补丁。实际官方结果为 **R_code=0、R_delivery=0**：唯一 FAIL_TO_PASS 测试 `test_issue_12420` 未通过，10项 PASS_TO_PASS 全部通过。评分器返回可解析的 `official_report`，补丁成功应用，未报告基础设施故障。

原回合是 `sympy__sympy-17318 / REVIEW2 / C1`，seed为 `2026110801560001`。其顶层 `controller-result.json` 缺失，原 `result.json` 仍保留 `technical_unknown`，没有伪造控制器正常退出或替换旧结果。

已封存的行政恢复审计证明：原受管工作已到 `bounded_work_closed`，没有执行完整性错误；observer原件为normal，presentations覆盖为true，其余原有coverage=false全部保留；原53次物理API请求均已结算，实际2,819,481 tokens；原唯一锁定树和合法REVIEW2交付同值，停止actor的1686个源码条目与锁定树一致，原控制器归档也已经完整验证。

新评分器精确匹配该审计、恢复结果SHA、原slot/config/seed、原patch SHA及锁定树；允许的只是审计指定的原native-code lock行政重定位。不复用需要“原child闭合结果存在”的旧恢复判断，也不再解压或扫描2.19GB原归档。合法交付仍调用项目既有合同验证器核验，缺失的observer覆盖不会被评分结果补成true。

评分使用原已合格的Sympy环境：只读重验v157保留的gold/empty资格及原control manifest，官方评分依赖、测试和基线不变；候选使用独立新run ID，没有借用旧候选评分缓存。

## 执行与资源

- 新独立目录：`runs/software-benchmark-v163/original-15703-rescore-r1`。
- 预检先在真实cold scorer解释器执行 `resolve_execution_request` 与 `validate_request`。
- 确认v157/v159主评分预约为空并记录协调release后，实际运行一个code评分容器。
- 容器限4 CPU、16 GiB，使用独立CPU位置116–119；`network=none`、`drop ALL`，无宿主绑定、GPU、出网或新模型调用。
- code与最后合法delivery完全同树，因此delivery复用本次真实code评分，没有再创建delivery容器。授权上限为两个，实际只用了一个。
- 容器清理已完成，`quiescent=true`、`cleanup_errors=[]`，本批active grader预约为零。

“合法提交存在”与“提交代码通过官方验收”是不同事实。本例的合法交付链已验证，但代码没有通过官方测试，因此delivery指标同样为0；不能把该结果解释为未完成提交流程。

主要证据：

- `artifacts/software-benchmark-v163/original-15703-rescore-r1/proposal.json`
- `artifacts/software-benchmark-v163/original-15703-rescore-r1/actual-request-preflight-r1/summary.json`
- `runs/software-benchmark-v163/original-15703-rescore-r1/coordinator/result.json`
- `runs/software-benchmark-v163/original-15703-rescore-r1/coordinator/same-tree-delivery.json`
- `artifacts/software-benchmark-v163/original-15703-rescore-r1/summary.json`

实现为新的scope/scorer/prepare/runner文件，未修改已冻结的v157/v159源码，也未修改原`software_benchmark_artifact_recovery_v163.py`或原模型记录。5项CPU控制覆盖精确原候选、保留原未知及coverage、拒绝其他slot/seed/condition，以及同树delivery不创建冗余评分器。
