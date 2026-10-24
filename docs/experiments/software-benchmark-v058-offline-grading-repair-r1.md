# v058：依据上游记录修订离线评分环境

日期：2026-10-24。**已完成项目代码修订和31项CPU控制；没有启动容器、网络、模型或正式评分。** 原共享服务器保护保持`hold=true`，历史候选、官方测试与成绩均未改变。

## 本次修了什么

| 改动 | 作用与边界 |
| --- | --- |
| 评分使用`network_mode=none`，服务仅在容器回环地址 | 新入口不导入或调用宿主NAT／keeper辅助模块，不执行宿主挂载、namespace进入或网络配置命令。真实超时夹具仅通过已核对身份的容器内执行接口准备。 |
| 固定依赖及证书语义 | 两道旧任务的httpbin服务使用0.7，避免0.4的`jsonify(headers.lists())`生成器兼容问题；给普通请求设置容器内`REQUESTS_CA_BUNDLE`。旧pytest-httpbin证书更新保留CN／无SAN语义，避免照搬新版证书破坏旧测试。 |
| 每题独立准入 | 一题必须有同一环境的参考修复通过和空补丁目标测试失败；其他题未合格不再阻塞它。完整四题、16候选计划分母保持。旧r2/r3控制不能冒充新v058资格。 |
| 保留局部异常与静止门 | 一条评分通道出现异常不妨碍另一条收集结果；如果不能证明自己的容器已静止，该通道仍停止派发。未启动的阻碍项不误触发静止失败。 |
| 修正新分析对未知项的处理 | 原队列继续保留旧评分证据；独立测量副本把环境未准入／补评未完成的项标为未知。它们不再被旧分析器当作已确认模型失败，任务数与不确定范围正确保留。 |

新增模块为`software_benchmark_grading_environment_v058`、`software_benchmark_grading_qualification_v058`和`software_benchmark_scorer_v058`；准入及16槽调度入口分别为`tools/check_ref_grading_environment_v058.py`、`tools/repair_ref_grading_environment_v058.py`。旧v056/v057源码与封存证据保留原样。

## 四题目前的准确状态

| 任务 | 既有r2参考解结果及当前判断 | v058允许的下一步 |
| --- | --- | --- |
| requests-2931 | 旧离线控制通过；保留其httpbin0.4／pytest-httpbin0.0.7组合 | 允许未来运行新的gold／empty环境控制；尚无v058资格 |
| requests-5414 | 旧离线控制通过；保留其httpbin0.7／pytest-httpbin1.0.0组合 | 同上 |
| requests-1766 | F2P全通过，P2P仍有`test_mixed_case_scheme_acceptable`失败 | 已知阻碍，禁止准入及补评，不重复运行无新解决办法的控制 |
| requests-1921 | F2P全通过，P2P还有Cookie过期、混合大小写HTTPS和pyOpenSSL重定向失败 | 服务兼容与普通请求CA配置已修订，但混合大小写HTTPS阻碍仍在，禁止准入及补评 |

两道旧题的精确基线均由`certs.where()`返回仓库内`cacert.pem`；混合大小写测试主动执行HTTP和HTTPS，且通过不读取CA环境变量的`Session.send()`调用。1921另有硬编码HTTPS地址，普通`request()`读取CA变量的路径可由新配置覆盖，但实际收益尚未验证。没有替换仓库CA、修改默认CA常量、关闭TLS校验、改官方测试或缩减F2P/P2P列表。

源码诊断依据：[1766固定基线certs.py](https://github.com/psf/requests/blob/847735553aeda6e6633f2b32e14ba14ba86887a4/requests/certs.py)、[1921固定基线sessions.py](https://github.com/psf/requests/blob/3c88e520da24ae6f736929a750876e7654accc3d/requests/sessions.py)。现有日志中其它原始FAILED项目并不全属于官方F2P/P2P；本次没有为了日志全绿而改动无关测试。

## 对照上游时采用与未采用的部分

- 参考[微软debug-gym](https://github.com/microsoft/debug-gym/blob/main/debug_gym/gym/envs/swe_bench.py)在容器内提供httpbin服务的方式；没有照搬其全部新版依赖，也没有修改宿主`/etc/hosts`。域名映射仅属于新评分容器。
- 依据[Requests官方说明](https://requests.readthedocs.io/en/latest/user/advanced/#prepared-requests)区分普通请求与prepared-request路径。环境变量不是对两种调用都有效的统一修复。
- [pytest-httpbin更新记录](https://github.com/kevin1024/pytest-httpbin#changelog)及[Requests PR #5869](https://github.com/psf/requests/pull/5869)说明新证书可能改变旧测试预期。上游通过修改测试解决的部分没有移入本轮固定官方测试。
- SWE-bench [#484](https://github.com/SWE-bench/SWE-bench/issues/484)的讨论为环境修订提供线索，但不是本轮四题的运行准入证据。

## 运行边界与验证

新provider在create/start首先检查既有硬暂停；还拒绝host或共享网络／PID／IPC、特权容器、SYS_ADMIN、宿主目录和设备、额外端口及安全配置覆盖。创建后核对实际配置和四类namespace身份，再准备容器内依赖。默认capability全部移除，只保留容器内真实超时夹具所需NET_ADMIN；独立服务配置还需NET_BIND_SERVICE，但对应两题当前禁用。CPU、内存、进程和swap约束明确固定。这些检查降低误配置风险，**不构成已经验证真实容器运行安全的结论**。

| 必要CPU控制 | 数量 | 覆盖 |
| --- | ---: | --- |
| provider mock控制 | 6 | 禁止配置、实际namespace／资源配置、阻碍项、服务／CA环境 |
| 逐题资格 | 16 | 完整计划、单题两控制、源码／镜像／候选绑定、跨题／跨端点复用拒绝、旧NAT证据拒绝 |
| 评分及调度集成 | 9 | 原候选／旧成绩保留、部分准入16槽、未知分析上下界、局部通道异常、11个资源入口的硬暂停 |

合计31项通过；Ruff通过。后补的两项只测试新发现的未知计数和通道异常路径，没有重跑无关整库测试。已一次核对现有本地资产引用并生成[环境清单](../../artifacts/software-benchmark-v058/offline-repair-r1/environment-manifest.json)，没有下载新资产。

具体来源哈希与控制结果见[validation.json](../../artifacts/software-benchmark-v058/offline-repair-r1/validation.json)。真实环境准入、16项补评与模型正确率收益均未取得；当前最多只有两题具备进入下一步环境控制的代码条件，不能说已有8份候选完成补评。
