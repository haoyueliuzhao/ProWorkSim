# v143：零模型启动接线修复

用户已批准原40题×S1／FREE2／REVIEW2共120回合、合计400元，并于2026-11-07更新AGENTS.md：不干扰共享服务器及其他用户的实验Docker操作无需逐次请求。此次继续完成原任务，不追加模型回合或现金预算。

## v142实际发生了什么

原v142激活完成当前httpbin端点探测并启动普通用户协调器，但第一个S1零模型诊断在actor初始化退出。实际错误是：新版managed worker调用的`worker.py`仍来自v130，后者强制旧公开测试结果revision，而actor配置已正确声明v141。这是执行接线缺陷，不是模型修复失败。

actor没有输出ready JSON，host又报JSONDecodeError；诊断汇总随后未检查失败状态便访问`controller_result`，再次报KeyError，遮蔽原始原因。新版本分别修复真实native校验器绑定与失败报告分支，保留原三份错误及对应日志。

本次实际消耗1个actor容器和1个专用卷，均有精确清理回执；controller没有创建，正式模型调用0、API费用0、评分0，原120回合均未调用。不能将服务启动解释为正式评测已进入，也不能宣称32GiB controller或大仓库运行已经验证。

## 恢复边界

原v141／v142封存源码及失败记录保持。v143是独立部署修订，使用同一预选题单、seed、成员／工具／提示协议、5M团队预算及原400元新账本路径。正式模型尚未启动，因此不会混入两种已运行配置的成绩。

原诊断1的对象身份不复用，新诊断5替代S1资格；诊断2／3／4从未消费，继续使用。追加一个诊断对的明确资源身份后，整批上限570个容器、125个卷，其余16生成对／4启动／2评分、112CPU／840GiB、无系统slice和GPU保持。旧诊断已消费1容器1卷计入累计，未消费的旧controller身份退役。

已完成的当前端点探测不重跑；新scope通过显式来源等价记录复用其原始结果，不伪称发生第二次探测。35题原评分资格仍只做必要来源绑定，修订环境的10个gold／empty控制均尚未执行。

只有本批精确归属的对象可被创建和清理。不改共享挂载、网络、驱动、系统资源组或他人任务。局部未定继续单列，无自动模型重采；共享身份、账单或清理完整性故障仍停止新派发。

## 修订验证与实际状态

CPU控制针对完整managed serve→native配置验证→ready路径，而不是只检查公测helper。诊断控制先保留原status、error、result引用及清理状态，再读取确实存在的controller字段；失败不以新的KeyError替代。

最终来源、验证结果和实际运行状态以本页后续补充及`artifacts/software-benchmark-v143/`回执为准。准备和CPU控制本身不计作新的模型成绩或实际容器资格。

## 实际恢复启动

新SOURCE SHA256为`b62b919f4f690015c37709697c392a7340952739c4a57e37f216aeda58922cfa`，修订提案SHA256为`880215a8dd85e559840224406915d8361a150cfefe4623bb12c818b7808a0e78`。派生授权明确依据原120回合／400元批准及后来新增的非干扰实验Docker通用权限，没有伪称用户逐字审阅过v143新提案。

修订服务已实际启动，诊断5已取得真实actor和controller ready；不重复原端点探测。此时仍为零模型准备，不能称120回合已运行。当前读取`runs/software-benchmark-v142/role-pilot40-r1/deployment-v143/api-coordinator`，不再把旧v142停止进度当当前进度。启动证据见[launch-status-r1](../../artifacts/software-benchmark-v143/launch-status-r1/summary.json)。

## 正式队列已进入

四个真实零模型诊断均通过；代表性大仓库controller峰值RSS为4,231,593,984字节（约3.94GiB），仅代表该初始化／闭合诊断，不等于完整5M回合峰值。新10项gold／empty控制均得到有效官方回执，五题分别gold=true／empty=false，最终40/40环境资格通过。

三组均已取得正式API结算回执，队列按原16生成／4启动／2异步评分配置运行。最新带时间快照见[launch-status-r2](../../artifacts/software-benchmark-v143/launch-status-r2/summary.json)；启动快照不代表120回合已结束或已有能力结论。三份组预算视图共享同一400元账本，不能重复相加。当前进度可用普通用户运行` .venv/bin/python tools/summarize_role_pilot_v143.py`只读查询；该新增分析工具不在已运行source闭包，不修改正在执行的代码。
