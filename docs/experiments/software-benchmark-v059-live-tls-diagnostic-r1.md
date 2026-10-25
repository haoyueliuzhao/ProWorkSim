# v059：1766／1921真实HTTPS诊断

日期：2026-10-25，北京时间。**两题的原CA与原Requests客户端均成功验证真实httpbin服务并取得HTTP 200；转发层在两次旧Requests请求的收尾阶段仍有错误，尚不能授予正式评分资格。** 本轮未运行gold／empty或模型候选评分，既有成绩未变。

## 实测结果

| 任务 | 原Requests版本 | 标准库＋原CA | 原版Session.send() | 转发协议收尾 |
| --- | --- | --- | --- | --- |
| requests-1766 | 2.0.1 | TLS成功，HTTP 200 | TLS成功，HTTP 200 | 标准库正常；旧Requests出现连接复位 |
| requests-1921 | 2.3.0 | TLS成功，HTTP 200 | TLS成功，HTTP 200 | 标准库正常；旧Requests出现连接复位 |

四个探针均正常退出，原CA文件SHA256前后相同，两个工作树保持清洁。标准库探针只加载原仓库CA，明确启用CERT_REQUIRED和主机名校验；原Requests使用自身Session.verify=True及原HTTPAdapter，没有传入verify覆盖值、追加CA或修改客户端函数。两题标准库握手均为TLSv1.2。

旧Requests两个探针均读取完236字节HTTP正文，返回status=completed。对应转发进程仍报`ConnectionResetError: [Errno 104] Connection reset by peer`并以1退出；原始transport.status=failed保留，不改写成成功。可能与旧客户端关闭连接和转发端EOF处理的配合有关，具体关闭顺序尚未完成定位。

因此可以支持的结论是：**在本次实际访问的服务端证书与网络条件下，两份旧CA及原Session.send路径能够正常完成TLS验证和HTTP请求。** 不能据此宣称转发实现已完整验证、官方测试全通过，或余下8份候选已经解决。

## 测试方式与边界

每题使用一个原始固定镜像，只核对其干净的官方初始仓库；没有应用参考补丁、候选补丁或官方测试补丁。容器内只在127.0.0.1:443监听。普通用户宿主进程通过Docker exec的双向流转发原始TLS字节，只主动连接一次解析后冻结的公网IPv4 `httpbin.org:443`；宿主不监听端口，TLS握手始终发生在容器内原客户端与真实服务之间。

每容器顺序执行两个探针：

1. 标准库SSLContext只加载原仓库CA，以httpbin.org为server_hostname，发送Connection: close的最小GET。
2. 原Requests从`/testbed`加载，调用`Session.send()`访问相同URL，不跟随重定向，完整读取受限响应后关闭。

两者均清除代理、CA、OpenSSL配置与SSLKEYLOGFILE环境覆盖。记录包路径／版本、CA选择路径与哈希、客户端退出状态及HTTP结果。没有运行错误证书／错误主机名行为反例，因此不能把这些静态设置和成功握手称为完整TLS安全认证。

容器配置仍为network=none，但**实际具有经过本次明确批准的受限出网能力**，不能标记为完全离线。Docker exec双向socket及非TTY流依据[Docker SDK文档](https://docker-py.readthedocs.io/en/stable/api.html#docker.api.exec_api.ExecApiMixin.exec_start)实现；转发器不创建TLS上下文、不解密或替换证书。

## 授权、资源与清理

用户对本次新增Docker等效权限操作和出网范围明确回复“授权上述限定诊断”后才启动。两容器串行，各2CPU／4GiB，swap不额外开放、pids上限64；默认capability全部移除，仅添加容器内NET_BIND_SERVICE，保留no-new-privileges。没有SYS_ADMIN、宿主目录／设备挂载、宿主端口发布、sudo、宿主namespace／mount操作、服务重启或路由／防火墙修改。

实际创建并清理2个容器，全部清理回执quiescent=true、cleanup_errors为空。共4次公网TCP连接、22,896字节转发载荷，未重试、未更换域名或CA、未关闭校验；该数值不包含TCP/IP头和内核预取，不能当作物理链路总流量。两题从创建开始到探针结束分别约3.80秒、2.64秒，均未触发120秒截止。

旧全局hold继续为true，v058授权保持completed。本轮v059授权也已关闭为completed，固定运行目录禁止重复执行。新增模型调用、官方评分调用和成绩变更均为0。

## 实现、验证及后续

新增独立的v059范围检查、受限TCP转发和诊断入口。37项必要CPU／假socket控制通过，覆盖公网地址限定、授权与旧暂停状态、Docker解帧、半关闭、流量和时间边界、普通标签继承、任务局部异常及精确清理。随后按授权进行上述真实测试，真实收尾错误没有被CPU结果掩盖。

下一步需修正并验证转发连接的收尾兼容，再设计正式评分需要的服务访问范围、连接并发和预算，并通过两题各gold／empty控制。该范围不同于本轮最多4次443连接的诊断许可，不能直接复用本轮授权启动正式补评。

- [结果与四个探针引用](../../artifacts/software-benchmark-v059/tls-diagnostic-r1/result.json)
- [具体测试范围](../../artifacts/software-benchmark-v059/tls-diagnostic-r1/proposal.json)
- [CPU控制记录](../../artifacts/software-benchmark-v059/tls-diagnostic-r1/cpu-validation.json)
- [已关闭授权](../../artifacts/software-benchmark-v059/tls-diagnostic-r1/completed-authorization.json)
- 本地完整记录：`runs/software-benchmark-v059/tls-probe-r1-20261025/`。
