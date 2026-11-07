# v147：Requests1766空闲连接造成评分未知的独立修订

2026-11-07。范围仅为原停止候选10103／10104及两个新的gold／empty环境控制；零模型调用，不修改已冻结v145／v146、原候选或原评分记录。该分支与v146真实API恢复队列独立。

## 事实与原因

v145两份停止候选的官方测试都运行到结尾：2 failed、89 passed。官方报告给出`resolved=false`、`infra_failure=false`；规定的FAIL_TO_PASS只有`test_DIGESTAUTH_QUOTES_QOP_VALUE`失败，PASS_TO_PASS无失败。其断言检查本地构造的Authorization头是否含带引号的`"auth"`，并非网络超时异常。另一个`pytest.raises`字符串调用TypeError没有进入该任务规定的失败测试集合，不能用它改写官方端点。

两次唯一传输异常都是连接4、端口80、上行730字节／下行988字节，60秒无新流量后被标记`upstream_idle_timeout`。各有68个正常TCP EOF和2个`evaluation_stopped`连接；传输线程、Docker exec和资源清理都结束，没有其他网络错误。整段传输分别持续93.50秒和82.93秒。

更关键的对照是原v143 empty控制：连接4也是730／988字节，但整段传输59.54秒，在该连接55.75秒时随评测结束按`evaluation_stopped`关闭，因此被接受。gold控制的连接4为732／988字节，在0.95秒收到EOF。**当前机制使相同类型的闲置连接，在测试总时长跨过60秒后变为技术未知。** 它并非要求所有TCP都必须EOF，而是没有区分正常持久连接空闲与未完成HTTP交换的空闲。

失败断言可能让pytest保留response／session对象至收尾，从而延迟连接释放；这是与证据一致的解释，尚没有逐连接HTTP分帧或测试映射证明，不能写成已确认的唯一原因。原始字节计数也不能证明响应完整。证据见[核查摘要](../../artifacts/software-benchmark-v147/idle-timeout-audit-r1/summary.json)。

HTTP/1.1支持持久连接；通过有效Content-Length或完整chunked分帧可以确定消息结束，无需等待TCP关闭。相反，在收到规定字节前超时或关闭仍是不完整响应。[RFC 9112消息长度](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3)、[持久连接](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.3)

## 本次有限缓解

仅在新Requests1766评分环境中将每连接空闲上限从60秒延长到180秒，官方测试总时限仍1800秒。每session仍最多512次连接／64MiB，端口仍限冻结的httpbin.org公网地址80／443。CA信任材料、严格TLS校验、容器隔离、官方测试和补丁保持；不解密443、不伪造EOF、不删除真实网络错误，也不依据旧字节数追认原结果。

此修改是有界缓解，不能保证测试更慢时不再遇到相同问题。彻底修复需增加可信HTTP请求／响应分帧及转发完成证据，再区分“已完成交换后的keepalive空闲”和“仍有未完成交换的超时”；443继续按不解密通道处理。

本次最多4个新容器，串行，分别为gold、empty、10103、10104；每个4CPU／16GiB，宿主评分进程4GiB且共用同4核。总TLS上限4 sessions／2048连接／256MiB。全部network=none、drop ALL，无宿主目录绑定、监听端口、GPU、服务创建、主机网络或挂载修改。只有这一已列明任务的容器私有网络能力用于评分。

实现：[独立评分器](../../src/proworksim/software_benchmark_rescore_v147.py)、[四项串行运行器](../../tools/run_requests_idle_rescore_v147.py)。2项必要CPU控制已通过：空闲80秒后由评测正常结束关闭，不冒充EOF；超过180秒仍记真实网络失败，连接数／总时间上限未放宽，原传输模块默认仍60秒。

## 实际验证进度

4项实际控评已经全部结束，新的官方资格验证通过；所有容器已按原身份清理，未发生模型调用或API费用。

| 对象 | 新修订官方结果 | 传输／清理 |
| --- | --- | --- |
| gold参考补丁控制 | resolved=true | 完整、已清理 |
| empty空补丁控制 | resolved=false | 完整、已清理 |
| 原停止候选10103 | resolved=false | 完整、已清理 |
| 原停止候选10104 | resolved=false | 完整、已清理 |

empty控制的连接4在82.45秒出现真实双向EOF；10103的同一连接在86.83秒出现真实双向EOF，待转发字节为0。两者都超过旧60秒门，证明这一限制会过早终止本来能够正常结束的连接；本次没有通过修改断言、伪造EOF或忽略网络错误取得结果。

两份原候选在新评分环境下都取得可信失败。新结果单独保存，原v145未知收据和原生成技术未知状态均保留，不能把停止工作树评分当作正常完成的模型回合。4项执行、实际连接／流量和清理证据见[真实控评摘要](../../artifacts/software-benchmark-v147/actual-controls-rescores-r1/summary.json)。
