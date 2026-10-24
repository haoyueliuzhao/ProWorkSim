# v057 requests 评分环境修复后的原候选补评协议

本次补评固定覆盖四个 requests 任务（1766、1921、2931、5414）及每题原来的四档预算，共16个已经结束、已经锁定候选的回合。选择依据是环境类别，不依据补评后的模型成绩；不重跑生成、不改变原补丁或候选树、不向任何Actor提供官方参考修复或隐藏评分。

## 准入与不变条件

只有同一冻结评分环境下，四题官方参考修复均通过、四题空补丁均不能通过目标测试，而且八个容器全部静止，才允许派发任何模型候选补评。`software_benchmark_grading_qualification_v057.validate_qualification`读取真实回执、原环境身份和静止证据，不仅检查一个passed标志。

新评分器`software_benchmark_scorer_v057`先调用原v056请求验证，保留`request.patch`、`native_candidate_lock`、题目、预算、模型、seed、基线映射、数据集和镜像身份。仅新增已准入的评分环境引用，并更换独立评分源码manifest、run ID和输出位置。官方harness与测试不改；环境准备发生在评分器的新容器中，不改变Actor权限。

评分环境r3使用评分专属的用户态NAT直连真实httpbin，保留独立容器网络命名空间，不调整主机路由／防火墙，不提供HTTP代理，也不向Actor开放网络。原请求中的`limits.network_mode=none`作为原配置证据保留；当前有效网络以冻结`environment_revision`、`grading_network_lane`和容器实际观察为准，新manifest明确标记评分网络改变。

补评准备阶段在其独立输出根下创建新的两个NAT keeper，不复用gold准入时的容器ID。新request、评分identity、receipt及静止证据都绑定自己的registry和lane。helper源码、CLI及slirp二进制配置必须与准入证据一致，宿主在派发前校验进程身份，评分器再核验实际Docker keeper及网络命名空间。

## 调度与失败处理

`tools/repair_ref_grading_environment_v057.py --execute --qualification <qualification.json>`先冻结16项计划与旧状态，再以两个独立评分通道运行，每项4CPU／16GiB。两通道复用原grader资源锁，保留128GiB磁盘与内存余量；候选不产生任何新GPU驻留。

普通评分异常留存原件后不阻断另一通道。若无法证明本通道创建的容器已静止，则只隔离该通道，避免叠加占用。已进入的补评不自动重试；所有输出使用新路径，原评分结果不覆盖。

全部已进入评分都证明静止后，工具清理本次新建的keeper和slirp服务；身份不一致或还有评分容器使用该命名空间时不得清理。原准入registry仅作为历史profile证据，不要求其旧PID继续存活，也不把它当作补评可用网络。

## 结果合并与统计边界

取得同候选、同条件且资源静止的可信官方回执后，保留完整旧评分字段于`prior_scoring_attempts`，再更新当前评分指针。新评分为false同样接受，不能只纳入成功补评。若新评分未知，不用未知或猜测覆盖原确定值，而是保留原值并加`environment_review=unresolved`；这明确表示该原分数尚未在修复环境中验证。

任务与生成记录完全保持。原分析不覆盖，新增分析位于独立补评目录的`analysis-r1`。其摘要和逐题CSV必须区分**16项修复环境评分、其余170项原环境的已评分回合，以及14项原生成技术未知**；不能称全200项在同一新环境下重测。

四个必要控制测试覆盖：旧生成及评分历史保留、新未知不冒充成功、不同候选／条件拒绝、原补丁与资格环境绑定。实际补评结果另以冻结计划、官方回执和合并记录报告，本协议本身不提前填入通过数。

NAT接入另增加三个必要检查：新的keeper不能冒用准入keeper、旧资源未静止时不得清理运行网络、不同评分lane回执不得混入同一候选。接入前实现和四项测试源码已精确归档于`artifacts/software-benchmark-v057/requests-rescore-pre-nat-r1/`。
