# v119：原50题PROJECT启动恢复

本次继续用户要求的[v118 PROJECT重测](software-benchmark-v118-project-rerun.md)，保留原50题、模型、非思考模式、5M上限、新seed及运行身份。v118在准备阶段停止，正式模型和唯一API中性准入均为0调用；已创建的2个诊断容器及1个卷全部清理。没有重采任何已调用模型的回合。

## 启动前实际发现与修正

**评分准备记录陈旧。** v118在本地资格准备之后又加强了scope校验，改变了其源码指纹；运行时环境清单因此与准备缓存不一致，按设计拒绝启动。新v119先稳定scope，再在独立目录准备48项复用资格和4个新TLS控制请求。封存步骤新增只读`--verify-preparation`，逐项比较当前offline、TLS、scorer清单、绑定和请求来源，确认最终源码与准备产物一致。旧失败和旧缓存不覆盖，也没有移除身份校验。

**公共夹具诊断要求过严。** v118真实Python3.9.20／pytest7.4.4环境中，HTTP和严格HTTPS都完成200响应，但诊断额外要求HTTPS响应JSON中的url也必须回显https。旧WSGI夹具回显http，且原Requests2931公开测试并不要求这个等式。v119去除该无依据门槛，保留真实HTTP／HTTPS请求、fixture CA及hostname验证、200状态和必要JSON结构；没有关闭TLS验证或再次更换证书。

新诊断使用index 2并实际通过：两个测试均通过，2次私有loopback连接、2个私有监听，0外部连接／子进程尝试／模型调用；原仓库CA、requirements和公开测试文件字节保持。旧index 1的false仍保留，未回改成通过。该诊断仅验证公开夹具，不是官方隐藏验收。

## 运行与预算

新协调路径为`runs/software-benchmark-v118/project-repaired-r1/api-coordinator-v119`，使用原普通用户服务的新生命周期`proworksim-v118-project.service`。生成与评分仍异步，最多16个生成pair和2个评分，112 CPU／576 GiB；旧累计现金上限350元保持，启动前可用195.65182408元。旧未定预约不释放。

本阶段最多302个容器、51卷，计入v118已消费诊断后累计上限304个容器、52卷。增加的是一次零模型诊断，不增加50个正式回合或API中性调用名额。所有正式身份、题单和seed逐字继承；4个原TLS控制只在新目录重新绑定请求，旧控制没有真正创建容器，因此不算控制重跑。

只管理本批新建对象，不使用GPU、宿主绑定或宿主监听，不修改共享服务器挂载、网络、驱动或既有他人任务。新实验已恢复启动；正式题数与成绩必须读取最新运行回执，不能把诊断或服务启动当作模型完成。

## 证据与边界

- [原未调用证明](../../artifacts/software-benchmark-v119/prior-call-audit-r1/summary.json)
- [指纹差异](../../artifacts/software-benchmark-v119/manifest-drift-r1/comparison.json)
- [未消费控制证明](../../artifacts/software-benchmark-v119/manifest-drift-r1/unused-control-evidence.json)
- [新评分准备及一致性控制](../../artifacts/software-benchmark-v119/grading-transport-control-r1/preparation.json)
- [公共夹具诊断修订控制](../../artifacts/software-benchmark-v119/public-fixture-contract-controls-r1/summary.json)
- [运行恢复控制](../../artifacts/software-benchmark-v119/runtime-controls-r1/summary.json)
- [完整恢复方案](../../artifacts/software-benchmark-v119/runtime-authorization-r1/proposal.json)，SHA256 `0eb14f8eb0b120a1054f81c41c8f677e6af377b1db97bc7b730029a234eb18fe`

v118／v119运行源码及准备产物均已封存，运行中不热改。实际结果由`tools/summarize_project_rerun_v119.py`按本批账本、代码评分及交付评分汇总；异常保留原身份并独立处理。封存工具有两处不影响执行的E702多语句样式提示，为保持已封存字节未做热改；运行模块和必要CPU控制通过。
