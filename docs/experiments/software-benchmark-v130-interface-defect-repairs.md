# v130：修复PROJECT工具说明与公开测试反馈

本轮针对[v129审计](software-benchmark-v129-project-defect-audit.md)确认的三个问题进行实现修复：文件路径参数说明错误、零测试被报告为通过，以及Requests公开测试依赖不兼容。新代码使用独立v130入口，旧实验源码、补丁、评分和账本保留。没有启动新评测、真实API调用、Docker容器或GPU，也没有修改共享主机配置。

## 修改后的行为

1. **文件读取参数与真实操作一致。** `read_file.path`明确表示仓库相对文件路径，`patch_id`才表示已发布的固定补丁。工具声明生成前逐节点复制可变对象，避免一个字段的说明修改连带影响另一个字段。相较原声明，只修正这处实际错误；保留v120的JSON对象键序等价、显式空游标、原参数拒绝和扣账逻辑。

2. **只有取得非零测试通过证据，才返回测试通过。** 新执行层读取pytest钩子、unittest结果及SymPy reporter的结构化计数，不从任意stdout中的“passed”文字推断成功。零测试、全部跳过／预期失败、无法确认计数、命令失败和超时分别记录；不会再把退出码0直接当成测试通过。`validation_status`、测试计数和证据摘要直接显示在PROJECT首屏及报告回读中，原始输出仍完整保存并分页。

   命令实际运行仍记为已执行，仍消耗原测试次数与时间；“测试通过”不等于隐藏验收通过。没有自动补跑测试、自动修补代码或自动提交，也没有改变原合法提交与最终官方代码评分的关系。REF的公开测试便利入口使用同一执行层；原生终端仍保留自己的操作能力。

3. **兼容旧公开测试，不改题目和断言。** Requests-2931使用独立私有依赖包：只为旧字符串形式的`pytest.raises`恢复调用者作用域中的异常检查，现代callable／context形式仍交给原pytest处理。缺少预期异常、错误异常类型仍会失败。httpbin的响应头生成器转换为字典后交给Flask JSON，保留多值响应头及Set-Cookie，其他JSON编码错误不被吞掉。保留原pytest分发、任务文件和既有私有localhost证书；不改变官方评分侧或宿主CA。

单动作、分页、版本绑定和受管交付仍是项目规则。本轮没有将多工具回复自动拆开执行，没有增加不受管bash，也没有根据隐藏测试或参考修复给模型补充提示。

## 实际接线

新PROJECT控制器使用`managed_v130 → tooling_v130`构造真实SDK工具；新actor的`ManagedOperationSession.execute`直接绑定v130测试执行函数。两组actor使用相同的依赖校验和测试结果版本，新控制器拒绝旧版ready记录，避免只增加辅助函数却继续运行旧实现。

公开测试执行器和计数器作为独立stdlib文件保留在私有runtime中，因此actor删除SDK私有包后，原生便利入口仍能调用它们。REF只清理本次命令的进程组；PROJECT额外保留原私有PID空间的子进程收口。没有在宿主挂载、修改网络、启动服务或操作其他用户进程。

新的[实现配置](../../config/v130-interface-defect-repairs.json)明确`implementation_only=true`、`execution_authorized=false`，未建立题单、seed或现金预算。未来运行需要使用新bundle、条件身份及对应部署范围，不能将本次实现混入已封存的50题成绩，也不能复用旧TLS诊断来宣称新环境已完整准入。

## 验证与限制

部署控制覆盖新身份、实际host构造路径、两组控制器输入、旧测试结果协议拒绝、actor执行函数绑定及零测试CLI退出状态。真实SDK组合控制使用固定脚本回复，检查实际工具、同一预算、一次自检、显式固定／提交与两个不同版本候选的闭合；没有调用模型。

测试计数控制覆盖真实pytest、unittest以及缓存SymPy测试框架的hash随机子进程。SymPy通过／零项／全跳过三个小fixture均返回预期结果。未知或重复计数报告、错误归属、stdout伪通过、超时和畸形JSON结构均不能产生通过信号；畸形记录返回局部“验证未知”，不抛成执行层崩溃。原`sitecustomize`钩子继续执行，普通断言失败不会再被标为测试收集异常。Django验证限于实际unittest基础runner，尚未运行完整Django前端。

Requests兼容控制使用缓存中的pytest 7.4.4与真实Flask WSGI `test_client`，先复现原`TypeError`／HTTP 500，再验证修复及反例。全部通过并不等于旧镜像中整套Requests测试已通过：本次使用本地Python 3.12，未启动原Python 3.9容器，也未运行基准任务全集。

本轮没有新的正确率结果。原恢复后对照仍为REF 36/50、PROJECT 33/50；这些修复是否提高分数、能提高多少，必须在新冻结评测中测量，不能由离线测试推定。

最终本地运行包为`runs/software-benchmark-v130/sdk-bundle-r2/`。r1仅是加入计数结构容错之前的离线包，未部署；原件保留。r2实际加载两组控制器、actor及真实SDK，通过新执行函数绑定和工具字段检查，导入阶段无网络、模型或额外子进程。打包检查用于确认实际部署包含修复，不替代任务镜像准入。

证据入口：[部署检查](../../artifacts/software-benchmark-v130/deployment-controls-r1/summary.json)、[公开依赖兼容前后对照](../../artifacts/software-benchmark-v130/public-compatibility-controls-r3/summary.json)、[独立依赖清单](../../artifacts/software-benchmark-v130/public-dependencies-r1/manifest.json)。完整收口索引见[实现验证汇总](../../artifacts/software-benchmark-v130/implementation-validation-r1/summary.json)。
