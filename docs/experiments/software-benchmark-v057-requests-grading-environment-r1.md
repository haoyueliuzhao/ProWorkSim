# v057 Requests 评分环境修复：实现与准入记录

日期：2026-10-24。**当前尚未取得四题完整准入，不可启动16个原候选补评。** 本文只记录已完成的实现和真实CPU控制；不会把准备阶段的局部通过写成完整环境有效。

## 问题与修复边界

v056四个Requests任务（1766、1921、2931、5414）均受评分环境问题影响。既有官方镜像固定不重拉，任务基线、候选文件、官方test patch及断言不修改；参考修复只进入可信评分端，Agent和原生成记录不接收评分材料。

四镜像均有Python3.9.20、pytest7.4.4，但缺少任务所需的httpbin、pytest-httpbin等依赖。原`network:none`没有10.255.255.1路由，连接超时测试立即得到NetworkUnreachable；旧测试还直接访问httpbin.org。新的环境只作用于独立评分容器，Actor网络边界不变。

## 已实现的环境组件

1. **固定离线依赖。** 从清华PyPI镜像直连取得26个wheel，共7,637,809字节，下载时清除代理。文件名、版本、大小、SHA256保存在`packages-manifest.json`。评分时只从复制进容器的本地wheel目录安装，禁止隐式网络下载。
2. **测试服务依赖。** 当前待准入配置固定httpbin0.7.0、Flask1.1.4、Werkzeug0.16.1等，并按任务使用pytest-httpbin0.0.7或1.0.0，补齐trustme和pytest-mock。httpbin0.4.0与该Python3/Flask/Werkzeug组合在response-headers端点处理generator时不兼容，故新配置不再使用它。
3. **真实超时路由。** 仅在评分专属netns中创建dummy接口`pwstimeout`，地址10.255.255.254/24，10.255.255.1没有应答端；用真实socket连接确认超时。无主机路由或防火墙规则修改，也不monkeypatch socket返回。设置对同一lane重复使用幂等。
4. **测试证书更新。** pytest-httpbin0.0.7自带服务器证书已于2025-06-23过期。只更新该依赖的测试CA、服务器证书和测试私钥，保留服务器CN=127.0.0.1、不增加SAN、继续验证证书。官方测试和候选`requests/cacert.pem`不改。生成命令、原/新哈希和有效期见`cert-renewal.json`。
5. **评分专属直连NAT接口。** legacy任务的直接HTTPS调用不一定读取REQUESTS_CA_BUNDLE，不能用更新候选自带CA文件来凑通过。新适配器将只加入两个明确拥有的grader keeper netns，由slirp4netns做用户态NAT，直接访问真实httpbin.org，不使用HTTP代理或反向代理。实际`network_mode=container:<owned keeper>`与历史`network:none`分层记录，不能冒称隔离条件未变。

代理环境变量在评分容器中清空，尤其不能保留`NO_PROXY=*`，否则会破坏Requests自身测试代理设置优先级的语义。此项与下载直连政策不同：下载仍禁代理，测试代码有权在自己的进程中构造代理变量并验证Requests行为。

依赖的证书行为与接口说明可参照[pytest-httpbin官方项目](https://github.com/kevin1024/pytest-httpbin)。曾尝试标准[OpenSSL配置](https://docs.openssl.org/1.1.1/man5/config/)对本地HTTPBIN域名证书增加局部信任；实际Python客户端对照仍失败，因此该方案未获准入，当前待验证方案不再启用它，也没有禁用TLS/hostname验证。

## 实际控制结果与目前限制

所有控制均使用原官方harness、同一任务镜像和基线，每容器4CPU/16GiB，两个评分lane。每题各执行官方参考修复和未修改基线；新目录、新run ID，原失败记录保留。

| 准备版本 | 2931参考解 | 5414参考解 | 1921/1766参考解 | 空补丁 |
| --- | --- | --- | --- | --- |
| r1：本地HTTP+离线超时路由 | 通过 | 代理变量测试未通过 | cookie/HTTPS等未通过 | 四题均正确拒绝 |
| r2：本地域名HTTP/HTTPS、清空NO_PROXY | 通过 | 通过 | TLS信任及历史服务兼容仍未通过 | 四题均正确拒绝 |
| r3：评分专属用户态NAT | 未启动完整准入 | 未启动完整准入 | 未启动完整准入 | 未启动完整准入 |

r1/r2所有控制容器已清理。其源码快照与失败回执保留在`runs/software-benchmark-v057/grading-environment-r1/source-revisions/`和两个`environment-admission-r*`目录，准备历史索引见[preparation-history.json](../../artifacts/software-benchmark-v057/grading-environment-r1/preparation-history.json)。这些是按官方参考修复检验环境的准备修订，不是根据16个模型候选的成绩选择配置。

NAT helper的首次实际生命周期控制造成共享服务器挂载异常；相关owned keeper和slirp进程已清理，新资源启动保持硬暂停。用户逐项明确授权后，已恢复全部已确认的原挂载可见性，详见[事故恢复报告](software-benchmark-v057-shared-server-incident-recovery-r1.md)。新增隔离实现没有获得真实运行资格，挂载恢复不自动解除暂停，也不自动恢复r3准入。

## API与正式补评门槛

- `software_benchmark_grading_environment_v057.freeze_environment(path)`冻结实际依赖、配置和适配源码。
- `EnvironmentContainers(..., observation, tracking=...)`要求`observation.environment_revision`及`nat_lane={registry: reference, lane: 0|1}`，校验keeper镜像／所有权／PID和grader网络namespace，并记录实际网络模式。所有资源只能由owned容器ID清理。
- `software_benchmark_grading_qualification_v057.validate_qualification(ref, original_request)`读取八个真实控制报告，要求四个gold全部成功应用且resolved，四个空补丁全部因目标测试失败而未通过，容器静止证据一致。再核对原任务的镜像、数据、基线映射及官方harness。

只有八项全部通过，才生成`passed=true`资格；正式补评还必须满足项目硬暂停已获明确授权解除。当前两项条件均未满足。已有模型代码不重新生成；补评结果须保留原评分并另记环境修订，不能把未完成准入或测试故障计作模型失败。

资格门的四项必要CPU测试已通过：同环境接纳、错镜像拒绝、任一gold失败或空基线成功时拒绝、owned容器静止证据不匹配时拒绝。适配模块、资格模块及控制工具Ruff通过；未重复运行全项目测试。
