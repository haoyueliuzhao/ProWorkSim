# v058 两题补评准备与权限边界

日期：2026-10-25。用户要求进行补评，同时继续处理1766／1921的评分环境问题。最新AGENTS.md明确禁止未经授权的root相关操作，因此任务授权与现有Docker管理接口的root等效操作授权分别记录。

**执行后状态：用户已先后明确授权原范围及追加4项控制；8份候选补评完成，6通过、2未通过。全部16个本轮容器已清理，授权现已标记completed，原全局hold保持true。** 下文中的pending描述是准备阶段记录；最终结果见[补评结果](software-benchmark-v058-rescore-results-r1.md)。

## 已准备的具体范围

已核对2931／5414在原四档预算下的8份候选补丁和候选锁引用。计划先运行两题各gold／empty，共4项环境控制；只有分别获得可信新资格的任务才能处理其4份原候选。题单与来源见[proposal.json](../../artifacts/software-benchmark-v058/rescore-authorization-r1/proposal.json)。旧16槽分母保留，1766／1921继续未准入。

申请范围为通过本项目既有Docker接口创建、运行及清理这些评分容器：最多并行2个，各4CPU／16GiB，network=none，无宿主挂载、设备、端口或GPU；drop ALL，仅添加容器内NET_ADMIN并保留no-new-privileges。没有守护进程启动／重启、宿主配置、系统服务或其他容器操作。后端若不可用，不通过重启服务自动修复。

仅检查了本项目socket与PID文件的元数据：socket可见，但PID文件未对应当前可见的进程，不能据此断言守护进程已停或正在正常运行。授权前没有连接Docker接口。

## 独立的窄范围派发检查

新增`software_benchmark_dispatch_v058`，只接受两题和11个明确的v058操作。授权文件为`config/v058-offline-rescore-authorization.json`；准备时状态为pending，获得具体回复后才改为approved。新模块不改变旧`v057-shared-server-hold.json`，原全局hold继续为true。执行完成后状态改为completed，不能自动再次派发。

放行必须同时满足：明确人工授权、固定任务／操作／资源约束、当前来源哈希一致、禁止自动释放、原全局hold完整。任务身份在这些检查通过后才解析，未知任务与扩大范围均拒绝。已知未准入项只返回无资源操作的阻碍记录，不因权限检查错误阻塞其他题。

这是一层项目工作流检查，不替代操作系统隔离。它未授权root shell、修改服务配置或启动旧NAT／模型入口。当前没有启动环境控制、评分、容器或模型。

原v058实现精确归档在[pre-scoped-dispatch-r1](../../artifacts/software-benchmark-v058/revisions/pre-scoped-dispatch-r1/index.json)，此前31项CPU控制保留其历史版本含义。本轮新增guard控制5项、受影响provider／控制器控制7项通过；Ruff通过。证据见[validation.json](../../artifacts/software-benchmark-v058/rescore-authorization-r1/validation.json)。

## 并行CA调查结果

官方方法仍未提供能同时满足“旧客户端、原测试、自签本地服务、原信任集合不变”的通用开关。`HTTPBIN_URL`不能避开测试主动切换HTTPS及硬编码域名；普通请求可读取`REQUESTS_CA_BUNDLE`，旧`Session.send()`不读取；`SSL_CERT_FILE/DIR`也不替代客户端显式加载的仓库CA。

新增诊断解释了旧r2的OpenSSL配置探针为何失败：实际OpenSSL3.0.15的`system_default`路径不启用`SSL_CONF_FLAG_CERTIFICATE`，而`VerifyCAFile`需要允许证书操作。因此加载配置返回成功不代表附加CA已经生效，不再重复更换`OPENSSL_CONF`写法试验。[对应OpenSSL源码](https://github.com/openssl/openssl/blob/openssl-3.0.15/ssl/ssl_mcnf.c)、[SSL_CONF_cmd说明](https://docs.openssl.org/3.0/man3/SSL_CONF_cmd/)

保留当前信任语义需要真实HTTPS服务提供原CA可验证的证书，现有离线环境不具备该条件。另一种方法是另立兼容性诊断，明确追加本地测试CA，并增加错误证书／错误主机名反例；它改变信任集合，不能冒充原官方评分。本次没有实施该变更，也没有解除1766／1921禁用。

准备阶段没有连接Docker或启动评分。随后发生的两次授权、实际容器操作、预检异常和成绩更正均另见[执行结果](software-benchmark-v058-rescore-results-r1.md)，不以准备阶段的零调用记录代替真实运行账目。
