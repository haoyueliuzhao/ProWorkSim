# v099：两项原候选的测试复位与离线构建修订

本轮已完成实现、CPU 验证及授权后的全部 6 个真实评分对象。两题均通过新的 gold=true／empty=false 环境控制；**原1675候选官方未通过，原5530候选官方通过**。新增模型调用为0，原补丁未修改；全部自建对象已清理，无清理隔离或取消。随后按用户要求停止扩展修复，剩余异常封存。

| 原槽 | 任务 | 新环境控制 | 原候选官方结果 |
| --- | --- | --- | --- |
| 1675 | Sphinx-11510 | gold通过、empty失败，鉴别成立 | 未通过（resolved=false） |
| 5530 | Astropy-7336 | gold通过、empty失败，鉴别成立 | 通过（resolved=true） |

原技术未知记录保留，新结果单独存于 `runs/software-benchmark-v099/two-task-rescore-r1/`。终态引用见 [补评结果](../../artifacts/software-benchmark-v099/terminal-summary-r1/summary.json)。以下记录实现和当时的准备边界，不表示仍待启动。

## 修复对象与证据

| 原槽 | 任务 | 已核实问题 | 修订 |
| --- | --- | --- | --- |
| 1675，DeepSeek REF 5M | Sphinx-11510 | 官方 eval 的整条 `git checkout` 混入 4 个基线不存在的新增测试文件，导致本应恢复的 `tests/test_directive_other.py` 也未恢复；原候选确实改过该文件，随后官方测试补丁失败。此外离线构建隔离环境无法下载 `flit_core>=3.7` | 按官方补丁路径逐项恢复／清除测试文件；在评分容器提供固定 flit_core wheel，原 pip 命令不变 |
| 5530，DeepSeek REF 5M | Astropy-7336 | 官方 checkout 指向重命名后的 `test_quantity_annotations.py`，该路径不在基线中，而且漏掉重命名前的 `py3_test_quantity_annotations.py`；原候选改过旧文件，官方补丁无法应用 | 对官方补丁的旧、新两侧路径做精确复位，再应用原字节补丁 |

原模型生成、候选锁、补丁、旧评分记录全部保留。测试修复不代表原模型候选必然正确；只能通过新的独立官方评分确定。

## 执行器修订的精确边界

1. 从原官方 `test_patch` 的两侧路径得到固定白名单，包含新增、删除、重命名的旧、新路径。仅支持本次两题已审阅的普通文本路径，不泛化到未知路径编码或二进制补丁。
2. 对基线存在的路径，从同一固定基线逐项恢复；基线不存在的路径只清除该精确文件或符号链接。拒绝符号链接父目录、目录型目标、重叠父子路径、`.git` 和路径逃逸；没有递归删除。
3. 官方 test patch 的 heredoc 逐字保留；若应用失败，在测试入口前明确退出。原评分器对此没有有效测试区段，`patch_successfully_applied` 不成立，仍归技术未知，不伪造正常失败。
4. 官方测试命令、测试结果解析、FAIL_TO_PASS／PASS_TO_PASS、评分规则均不变。测试后的复位也使用同一固定白名单。
5. 原 `TestSpec.eval_script` 是只读属性，且 `make_test_spec` 会加入测试退出码记录。实现先用实际官方 builder 得到运行脚本，再复制 `eval_script_list`，保留原退出码记录；不修改原 spec、SDK 安装或全局模块。

评分时本来就要恢复官方测试 preimage 后应用官方测试补丁。本次修订修复这一步的执行失败；它仍是独立的评测执行器版本，不能与旧失败记录悄悄混用或称为纯模型改进。

## 离线依赖

固定 `flit_core==3.9.0`，wheel 为 `flit_core-3.9.0-py3-none-any.whl`，63,141 字节，SHA256：

`7aada352fb0c7f5538c4fafeddf314d3a6a92ee8e2b1de70482329e42de70301`

本机原 Sphinx baseline 的 build-system 仅要求 `flit_core>=3.7`，项目要求 Python>=3.9，原容器为 Python3.9.20。该 wheel 要求 Python>=3.6，纯 Python、无额外 Requires-Dist。已由主代理国内直连下载，并核对官方元数据、镜像哈希和 wheel 元数据；没有通过代理或安装到宿主环境。

来源为 [清华镜像固定 wheel](https://pypi.tuna.tsinghua.edu.cn/packages/38/45/618e84e49a6c51e5dd15565ec2fcd82ab273434f236b8f108f065ded517a/flit_core-3.9.0-py3-none-any.whl)，本地来源记录在 `runs/software-benchmark-v099/offline-wheel-preparation-r1/downloaded-wheel.json`。

只有 Sphinx 的三个新评分容器会得到该文件，通过原官方 `copy_to_container` 传输；新 `put_archive` 只接受该精确名称、大小和哈希的单一文件，改为容器内 root-owned 0444 元数据，避免无 DAC_OVERRIDE 的 root 读不到上传文件。没有宿主绑定目录。

仅这些评分容器加入 `PIP_NO_INDEX=1`、`PIP_FIND_LINKS=file:///pws-v099-build-wheels` 和禁用 pip 版本检查的环境变量；原 `pip install -e .[test]` 命令保持。容器 `network=none`；若发现其他缺失依赖，应记录为新的环境问题，不启用网络、不自动换依赖或评分配置。

## 必要验证

| 控制 | 范围与结果 |
| --- | --- |
| 两项真实 Git 复现 | 使用原 baseline/terminal snapshot 的测试 preimage 和原官方 test patch，在 `/tmp` 独立 Git 仓库中复现旧 checkout、apply 的失败。修订后两题测试路径均与“干净基线＋原官方补丁”逐文件字节和模式等值；最终复位回到原基线路径 |
| 候选非测试内容 | 隔离 fixture 同时包含原候选变更的全部非测试文本文件：Astropy 92 个、Sphinx 157 个，修订前后字节和模式保持。fixture 是真实原件的投影，不是完整容器执行；二进制文件未在这项文本投影控制中重物化，执行器的写入白名单也不包含它们 |
| 4 项复位单测 | 冲突新增文件清除、候选代码保持、符号链接父目录／目录目标拒绝、坏路径和缺基线拒绝、官方补丁失败前置退出；0.20 秒通过 |
| 4 项评分接入单测 | 实际新 `Containers.create → ObservedContainer.start` 的环境和 ownership 绑定；执行原官方文件传输 helper；精确 wheel 归属和内容校验；拒绝缺少离线设置、外部容器和未知归档成员；0.24 秒通过 |
| 6 项隔离 `-m --validate-request` | 原评分器的真实请求、claim、原候选锁、generation quiescence 和完整 gold／empty 资格校验执行。4 control＋2 原 candidate 通过，CPU fixture 的控制结果完全是 `/tmp` 合成元数据，不能当成真实控制成绩；该 CPU 授权明确拒绝创建容器 |

Ruff 通过。首次准备发现旧安装清单要求 `maximum_real_tls_sessions` 字段，已明确置 0；首次 CPU fixture 漏建临时父目录，修复后通过。原失败准备输入保留，均在 Docker／模型前发生。未为了通过检查放宽候选、资格或权限规则。

证据：[原件 Git 控制](../../artifacts/software-benchmark-v099/test-reset-control-r1/summary.json)、[隔离评分器校验](../../artifacts/software-benchmark-v099/isolated-scorer-control-r1/summary.json)、[最终封存](../../artifacts/software-benchmark-v099/rescore-authorization-r1/final-seal.json)。

## 六对象独立执行计划

新入口为 `tools/run_rescore_v099.py --run`；它在获得精确 approved 授权后才可运行。准备阶段只执行 `--prepare`，随后由主代理按明确范围授权并串行完成全部6对象。对应 proposal 在 [本轮范围](../../artifacts/software-benchmark-v099/rescore-authorization-r1/proposal.json)。

- Sphinx gold、empty 按次序执行，原完整资格验证通过后才准备并评分原1675候选。
- Astropy 同样先 gold、empty，资格通过后评分原5530候选。
- 技术异常且清理可信时记录异常、继续另一题；该题控制不合格则不评分其候选。若自建容器清理无法证明，保留占用凭证并隔离后续运行，不冒险复用容量。
- 每个身份最多进入一次，不自动重试，不重新生成模型，不选择其他代码版本。输出保存在独立 v099 根目录，run_id 与旧评分不同。

最多 6 个容器、并发 1；容器各 4 CPU／16 GiB，评分宿主进程同四核、4 GiB 地址空间。`network=none`、`drop ALL`，无新增 capability、端口、GPU、named volume、宿主目录绑定、服务、slice 或宿主配置操作。普通用户运行器在主机可用内存≥24 GiB、目标盘空闲≥16 GiB 时才申请单个评分对象。所用四核延续原固定 grader lane。

新 scope 精确绑定两份原请求、原配置、原唯一候选锁和旧闭合记录；原 `_generation_result` 仅把读取根目录绑定回旧 episode 位置，其余候选校验完整沿用。新资源 claim、控制、资格和评分归独立目录；完成后只清理本轮自建对象。

准备时没有 approved AUTH，CPU 控制未替代真实结果。现两份独立资格文件与两份官方评分回执均已形成；源码和结果冻结，不自动追加对象或重跑模型。运行器 `completed.json` 中的通用 `runtime_qualified:false` 是准备时遗留的固定汇总字段，不能替代逐题资格判定；本次两题是否准入以各自 `qualifications/*.json` 及其 gold／empty 证据为准，此处保留原字段，不回改运行原件。
