# v154：三项评分未定的原因修复与最终判定

2026-11-08。仅处理v146正常模型闭合、v149已锁定的10214、10215、10219三份原候选；没有重新调用模型，没有修改候选或旧评分记录。

| 身份 | 实际结果 | 判定依据 |
| --- | --- | --- |
| 10214，REVIEW2，Requests1766 | 代码通过、合法交付通过 | 新官方评分通过；合法交付与代码同树，复用该官方收据 |
| 10215，FREE2，Requests1766 | 代码通过、合法交付通过 | 新官方评分通过；同树合法交付复用，无重复评分 |
| 10219，REVIEW2，pytest6197 | 候选执行失败 | 新环境下安装成功、补丁应用成功，但官方pytest入口实际因候选文件导入报NameError；独立证据判定，不冒充可解析的官方测试报告 |

## 两项系统缺陷

Requests的旧错误不是CA验证或远端连接故障。v150选择了idle180环境清单，但只修改了`provider()`与`request_fields()`；实际`Containers.create()`仍直接实例化标准TLS类。标准类在启动时读取idle180清单，立即报`Frozen grading environment changed`，尚未执行CA探针或网络传输。v154将实际构造路径绑定到同一已验证的idle180提供者，保留严格TLS、CA及原测试；必要CPU控制直接经过真实构造分支，而非只检查声明的provider。

pytest6197的官方`python -m pip install -e .`启动隔离构建，需要原pyproject规定的setuptools、setuptools-scm和wheel。旧评分容器禁网却没有提供这些构建依赖。v154仅向自有容器上传6份本地已固定版本wheel，设置离线查找路径；不下载、不使用代理、不安装宿主软件、不关闭构建隔离、不改官方pip命令。两个任务各进行了新的gold／empty控制，均得到gold通过、empty失败并完整清理。

## 10219为何不能继续归为网络未知

修订后真实日志证明：构建依赖安装、editable构建和pytest安装均成功，网络错误消失；原补丁也已应用。随后官方pytest命令导入`src/_pytest/python.py`时，在第1行出现`NameError: name 'placeholder' is not defined`。锁定候选与基线相比只修改这一文件，将原内容替换为该单一未定义名称表达式。

原始官方报告现为`resolved=false`、`infra_failure=false`、`patch_successfully_applied=false`；最后一个字段同时反映没有可解析测试结果，不能直接解释成git应用补丁失败。原包装层因此仍记录`technical_unknown/null`。这些原值全部保留，另以`candidate_execution_failed`、`resolved=false`、`basis=validated_candidate_failure`记录可证的候选执行失败，**没有把它改名为`official_report`，没有编造逐项测试成绩**。[具体证据](../../artifacts/software-benchmark-v154/final-assessments-r1/pytest6197-candidate-failure-proof.json)

该证据证明留存候选导致了实际导入失败，但没有单独证明这一变更是模型主动产生、工具处理产生还是导出环节产生；本次不据此评价模型推理能力，也不扩展调查或修改候选。

## 收尾与汇总入口

本轮实际创建7个容器：4个环境控制、3个原候选评分，均已清理。最后只读查询这7个准确自有ID，全部返回404，私有活动资源声明为空；没有列出其他用户容器。没有新卷、模型调用、API费用、GPU或共享主机配置修改。[执行与资源摘要](../../artifacts/software-benchmark-v154/execution-summary-r1.json)

最小规范合并入口为`runs/software-benchmark-v154/three-score-recovery-r1/canonical-overlay.json`的`canonical_results`。逐项保留`slot_id`、`state`、`resolved`、`basis`与`official_status`；10219另保留原始官方字段及独立证据。旧v151记录不覆盖。

只读汇总器v152已经实际合并：FREE2的11项恢复结果全部明确，代码6项／交付6项通过；REVIEW2的10项全部明确，代码6项／交付5项通过，其中9份可解析官方评分、1项可证候选执行失败。当前恢复面板剩余未定为0；不能把后一类包装成普通官方评分。恢复批次实际API结算80.34645796元、已知92,310,090 token，累计450元账本余量18.83989024元；本次v154新增API消耗为0。[完整42身份及选定21项汇总](../../artifacts/software-benchmark-v154/recovery-chain-summary-r1.json)
