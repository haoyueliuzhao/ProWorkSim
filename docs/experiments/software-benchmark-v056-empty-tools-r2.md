# v056 大预算摘要请求修复与未开始库存接续

日期：2026-10-24。原50题×四档预算、全部200槽、seed、模型、上下文、输出、公共工具和预算值均保持。旧运行记录与源码已归档；这次没有重跑已经进入模型的槽。

## 发现的问题

原始REF 50万预算通常在40次Agent调用之前结束，旧正常回合没有触发原生历史摘要。提高累计预算后，首批高预算回合触发SDK condenser，其请求含`tools: []`和`tool_choice: none`。vLLM0.32.0在请求校验阶段拒绝空工具数组，返回HTTP400；模型服务本身保持存活。

首批10槽已实际进入模型：2个50万槽正常预算闭合并完成官方评分，8个高预算槽在40次完整Agent响应后，第41次摘要请求遭遇此错误。8个错误按技术未知保留，不填模型修复失败、不重采。等待队列的新派发已暂停，在途原版本回合独立结束，六个真实模型驻留未重载或停止。

## 独立修复和必要验证

新`BudgetRefAdapter`对工具为空的摘要请求省略`tools`和对应`tool_choice`，精确计数、保存请求和实际派发均使用同一规范形式；Agent的五工具请求不变。新counter保留固定tokenizer、完整input_ids、原始响应及用量核验；预算预约、原采样、32,768输出、512次及6／6.5小时规则不变。

必要CPU控制通过。真实HTTP控制只对已失败的请求做tokenize，不重新生成该题：原形式和省略字段形式均为4,898个完全相同的input_ids，并与旧原件一致。之后只做一次独立中性请求，返回200、输入24＋输出119＝143 token，其中思考115；这143 token单列为准备成本，不计正式任务。没有自动重试。

## 接续范围

新源码与绑定在`artifacts/software-benchmark-v056/runtime-r2/`。独立队列`runs/software-benchmark-v056/queue-r2`通过有来源的接续记录保留原10槽，**仅接续190个从未派发、从未claim的pending槽**。旧job目录、原结果、异常和计费记录均保留。每槽标明r1／r2，分析不能把全200槽描述成单一未变程序版本。

生成、评分和模板回收仍异步；单题异常进入集合，其他任务继续。评分必须证明自己创建的容器已静止，才释放对应评分资源；正常评分异常不长期占住评分池。任务完成后自动汇总结果并仅释放本轮所有的GPU驻留和符合四档终态、静止、锁条件的缓存。

凭据：[协议与真实HTTP控制](../../artifacts/software-benchmark-v056/empty-tools-protocol-r2/result.json)、[tokenizer同值](../../artifacts/software-benchmark-v056/empty-tools-protocol-r2/tokenizer-equivalence.json)、[原10槽分类](../../artifacts/software-benchmark-v056/runtime-r2/predecessor-slot-classification.json)、[r2绑定](../../artifacts/software-benchmark-v056/runtime-r2/bindings.json)。

公共系统故障的修复是本次技术修订；没有使用任务成绩选择新题、改提示、增补失败样本或重选候选。更大预算是否带来正常结束及正确修复的改善，仍以剩余固定库存的完整结果和保留的未知边界为准。
