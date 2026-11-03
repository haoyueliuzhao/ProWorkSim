# v116：Requests评分CA路径修订与剩余恢复范围

本说明承接[v114未定回合处理方案](software-benchmark-v114-unknown-recovery.md)。用户已允许评分侧更新CA；**本次新增4个环境控制容器及4个TLS session仍待具体授权，v116尚未启动新的评分或模型生成。** 原评测题目、模型配置、候选补丁及历史结果均不改写。

## 已完成的处理

v114实际使用8个容器，完成两道测试恢复修复题的4个gold／empty控制，以及4份既有候选评分：REF 7232未通过、7283通过；7244和7251的停止树补充候选均未通过。后两项仍单列为`recovered_stopped_code`，不把原生成技术中断改写为正常完成，也不重跑模型或增加token统计的任务分母。

v115随后实际运行了4个Requests环境控制。两道gold的FAIL_TO_PASS测试均已通过，先前的HTTP 502已消失，但PASS_TO_PASS仍有TLS失败：1766的`test_mixed_case_scheme_acceptable`，1921另有`test_pyopenssl_redirect`。测试名称不代表实际启用了PyOpenSSL；保留的调用栈均经过标准`_ssl`。

日志显示，这些调用从Python环境中已安装的Requests包加载CA。旧shim只覆盖`/testbed/requests/cacert.pem`，因此未处理以下固定路径：

`/opt/miniconda3/envs/testbed/lib/python3.9/site-packages/requests/cacert.pem`

两份安装日志分别记录了已有Requests 2.0.1／2.3.0，但版本元数据不能证明CA字节相同。因此保留运行前的双路径校验；任何路径缺失或哈希不符，都在官方测试前明确失败，不猜测或放宽信任。

## v116修复边界与验证

新[CA模块](../../src/proworksim/software_benchmark_grading_ca_v116.py)仅将上述installed路径加入原源码路径的允许集合。两份CA都必须保持各自任务已冻结的原SHA256；实际SSL加载时再次校验，才映射到评分专用bundle。其他`cafile`、`capath`、`cadata`透传，不改证书验证模式或主机名校验。

公开CA、原CA和合并bundle逐字复用v114；新增的仅是v116路径映射shim与profile，容器目录为`/pws-fixtures/ca-v116`。**有效信任集相对原始环境已改变，但相对v114没有再次扩充CA；原CA文件及预测补丁保持不变。** 新profile位于`runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json`。

[4项CPU控制](../../artifacts/software-benchmark-v116/grading-ca-controls-r1/summary.json)已通过：两个原Requests版本分别在临时源码布局和installed布局中，实际执行`certs.where → HTTPAdapter.cert_verify → urllib3.ssl_wrap_socket → 原生SSLContext加载器`，仅最后的socket包装采用脚本替身。控制未伪造loader属性，验证了路径选择、CA哈希约束及校验状态保持；网络、Docker、API操作均为0。这些CPU证据不代替真实评分容器中的新gold／empty资格。

## 新增范围与累计上限

原26个容器额度已使用12个，剩余14个；完成原定剩余工作最多需要18个，因此需增加4个环境控制容器。4个原未调用回合仍是首次生成，模型策略继续使用已冻结的v110实现，不启用另行准备的历史解析修复。

| 本阶段工作 | 容器上限 |
|---|---:|
| Requests1766／1921新gold／empty控制 | 4 |
| 原4回合的生成环境，每回合actor＋controller | 8 |
| 新生成候选的代码评分 | 4 |
| PROJECT最多两份独立交付评分 | 2 |
| **本阶段合计** | **18** |

累计上限由26调整为**30个容器、4个专用卷**。本阶段TLS最多10个session；计入v115已使用的4个，累计最多**14个session、7,168次连接、896 MiB应用载荷**，仍为每session最多512次连接／64 MiB。不是重新开放已用的旧对象或重置计数。

继续使用原累计**350元API账本**，不增加现金预算；原4回合生成上限仍为合计20M输入＋输出token。并发与资源上限沿用原方案：最多4对生成和2个评分，40 CPU／192 GiB；HTTP评分串行，异常独立留档，不自动重采已调用回合。

本次不修改宿主CA、挂载、网络、守护进程或其他用户任务。v114／v115源码与证据保留冻结；只有新授权范围获准且新控制合格后，才可启动相应后续工作。通过率与token分析将保留原正式口径，并另列包含停止树补充评分的候选端点口径。

具体增补范围已封存在[proposal.json](../../artifacts/software-benchmark-v116/runtime-amendment-r1/proposal.json)，SHA256 `eaabade4a3cedfd0afb5c6075963a56a5ed40d373a24b8a6afd18080797ef42e`。本次封存仅生成prepared方案和源码清单，未写approved授权；不能据此启动。
