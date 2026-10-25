# v058 原候选补评结果

日期：2026-10-25，北京时间。**本轮8份原候选全部完成补评：6份通过、2份未通过；另8份仍属评分环境未知。** 新模型调用为0，原补丁未修改。

## 逐题结果

| 任务 | 50万token | 200万token | 500万token | 1000万token |
| --- | --- | --- | --- | --- |
| requests-2931 | 未通过 | 通过 | 通过 | 通过 |
| requests-5414 | 未通过 | 通过 | 通过 | 通过 |

这8份候选的旧评分均为false。新结果中6份变为true；原始评分保留在历史记录中。实际传入容器的8份补丁SHA256及长度均与原锁定补丁相同，见[传输及权限证据](../../artifacts/software-benchmark-v058/rescore-results-r1/transfer-and-capability-evidence.json)。

这表明原来的false不能继续被解释为这6份代码没有修好问题。变化来自评分执行与环境修订，不是重新生成、人工修补或训练收益；本轮没有分别消融每项环境修订，不能把翻转全部归因于某一个依赖或证书设置。

## 准入、异常与实际操作

| 阶段（北京时间） | 实际结果 |
| --- | --- |
| 09:08:37—09:08:43，首轮预检 | 官方harness默认请求SYS_ADMIN，被项目包装器在Docker create之前拒绝。0个容器创建，未进入官方测试。 |
| 09:11:06—09:11:49，首批4个控制容器 | 删除上述默认权限后，容器能启动；但普通用户上传tar的文件属主与容器root不同，600模式的patch/eval文件无法读取。4项均未到达有效测试，全部容器已清理。 |
| 09:16:13—09:17:53，用户追加授权的4个控制 | 修复tar属主后，两题各gold通过、empty按目标测试失败，分别取得新环境资格。4个容器均清理。 |
| 09:19:39—09:23:00，8份候选补评 | 8份均取得可信官方评分，6通过、2未通过，8个容器均清理。 |

有效环境准入耗时约99.9秒，候选补评阶段墙钟耗时约200.2秒。准备和修订时间未算入这两个数值。所有失败预检及修订版本均保留，不把它们记成模型失败，也不伪装为首次准备即通过。

本轮共实际创建16个容器：首批4个控制、追加4个控制及8个候选评分。各自清理回执均为quiescent=true、cleanup_errors为空，未发生资源创建结果不明。每次最多2个容器、各4CPU／16GiB，network=none；实际capability仅NET_ADMIN，默认capability全移除。没有SYS_ADMIN、宿主目录／设备挂载或端口发布。

## 为遵守授权作出的启动修订

旧评分启动器会进入user／mount namespace并执行mount/chroot，本轮未使用它。新`run_offline_scorer_v058.py`以普通用户进程直接调用已有私有ELF loader与原Python3.12.3，拒绝root进程启动，固定scorer包优先级，不继承LD_*、代理和API密钥。

真实metadata/import控制确认：相对旧manifest，唯一差异是Python可执行文件从chroot内的`/usr/bin/python3.12`重定位到对应物理路径。解释器字节、Python版本、全部依赖和官方评分源码一致。v058仅允许这一处路径差异，不伪造sys.executable，见[启动控制](../../artifacts/software-benchmark-v058/host-python-launcher-r1/control.json)。

普通用户上传产生的tar UID/GID问题，通过只调整容器内文件所有权解决；补丁和eval脚本的字节、文件名、权限位保持。没有为读取文件增加DAC_OVERRIDE或SYS_ADMIN，也没有修改官方harness源码。

用户分别明确回复“授权上述限定范围”和“授权追加这4项控制”后才进行相应操作。宿主命令保持普通用户；Docker管理操作使用已授权的接口。未运行sudo、宿主mount/unshare/chroot、网络辅助程序，未修改宿主路由、防火墙或系统服务，未重启Docker。既有全局hold保持true；本轮窄授权完成后已关闭，见[授权关闭记录](../../artifacts/software-benchmark-v058/rescore-results-r1/authorization-closed.json)。

## 预算面板的新测量状态

原预算实验仍为50个不同任务、每题四档预算，共200回合。生成结果、token消耗及停止原因不变。当前可确认评分178项，未知22项：原生成技术未知14项，加上1766／1921各四档的8项环境未知。178项中包含170项原环境结果与8项修订环境结果，不是全部重新评分的同一环境面板。

| 每回合预算 | 已确认成功数／计划50题 | 技术未知 | 完成率可识别范围 |
| --- | ---: | ---: | ---: |
| 50万 | 12／50 | 2 | 24%—28% |
| 200万 | 23／50 | 4 | 46%—54% |
| 500万 | 21／50 | 8 | 42%—58% |
| 1000万 | 22／50 | 8 | 44%—60% |

这些范围仅将未知项分别按全部失败／全部成功计算，**不是统计置信区间**。已确认成功总数由72增至78。旧队列中的成绩证据保留；新分析使用独立测量副本，将环境未定项标为unknown，避免把旧false误计为已知模型失败。原报告作为历史版本保留，本表及新分析对应本次补评后的状态。

## 尚未解决的两题

1766／1921仍无法在“原客户端、原测试、自签本地服务、原CA信任集合”条件下通过混合大小写HTTPS测试。普通请求的CA配置修订不能覆盖旧`Session.send()`；OpenSSL的system_default配置也不能据此追加所需信任。两题各四份候选继续标为环境未知，不改官方验收、不关闭TLS验证、不伪造成功。

并行调查提出一种尚未实施的后续方案：通过明确拥有的评分容器的Docker exec双向通道转发原始TCP字节，由普通用户宿主进程直连真实httpbin，保留客户端到真实服务的TLS验证。这需要新的评分出网授权及独立实现／准入，不能因为容器配置仍写network=none就当作没有出网。官方API能力见[Docker SDK](https://docker-py.readthedocs.io/en/stable/api.html#docker.api.exec_api.ExecApiMixin.exec_start)。它不能预先保证旧CA可以验证当前真实服务，也不能保证公共服务稳定；本轮没有建立该通道或增加公网连接。

## 证据

- [汇总及逐候选引用](../../artifacts/software-benchmark-v058/rescore-results-r1/summary.json)
- [逐候选CSV](../../artifacts/software-benchmark-v058/rescore-results-r1/candidate-results.csv)
- [原候选与授权范围](../../artifacts/software-benchmark-v058/rescore-authorization-r1/proposal.json)
- 本地完整回执：`runs/software-benchmark-v058/environment-admission-r3-approved-20261025/`与`requests-rescore-r1-approved-20261025/`。

原v056及v058的CPU控制保留。此次只对新增或变化的授权、解释器启动、路径重定位、最小权限及tar传输作针对性CPU检查，并完成上述真实控制和评分，没有重跑模型或整库测试。
