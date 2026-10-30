# v097：评分环境探针与 TLS 收尾的独立修订

本次完成代码和离线 CPU 控制，**没有启动容器、模型、API 或网络连接，也没有重新授予环境资格或改写旧成绩**。新增实现按需绑定到新评分器，旧 v066–v096 源码保持不变。

## 已核实的故障与处理

| 对象 | 现有证据 | 本次处理与边界 |
| --- | --- | --- |
| Requests-1724，gold/empty | 容器解释器执行 `os.sched_getaffinity` 报 `AttributeError`，尚未进入官方测试 | 新探针优先使用该 API；旧解释器缺少 API 时读取当前进程 `/proc/self/status` 的 `Cpus_allowed_list`。仍要求实际 CPU 集与预约的四核完全相等；没有降低资源边界要求 |
| Pylint-8898，gold/empty | 原探针 `json.loads` 从首字符失败。旧日志未留存原 stdout，无法确认是空输出、启动噪声还是其他原因 | 使用 `python -S` 执行仅依赖标准库的内核探针，独立 stdout/stderr，读取唯一带标记的 JSON 帧；保留退出码、原输出、长度和哈希。空帧、多帧、非法值及执行失败仍拒绝。此项是明确的诊断与解析修订，不能声称已证明原始故障原因或真实环境已修复 |
| Requests-1921 | 旧 gold 官方 resolved=true、empty=false，但官方清理删除容器后才读取最终 CA，得到 404，资格保持未知 | 复用已有 v068 修复，将收尾钩子安装到实际传入 evaluator 函数的私有 globals。CA 读取和传输收尾发生在原清理调用前；不是改全局模块同名函数。读取失败仍清理并记录异常，不得当作合格 |

探针只读取自身 CPU/namespace 记录。它不使用任务代码或第三方包，不修改任务文件、CA、TLS 校验、测试、补丁、网络、挂载或资源限额。`-S` 只影响独立探针，不改变官方测试 Python 的运行方式。

## 实际接入入口

`software_benchmark_grading_repairs_v097.bind_scorer(existing_private_scorer)` 返回新的私有评分模块，保留调用方的任务、候选、资源身份和权限校验。

新模块的 `Containers.create` 实际指向新 `ObservedContainer.start`；`_score` 实际读取带 v068 `run_official` 的私有环境对象。新 manifest 记录两个 v097 文件和 v068 生命周期适配器。已冻结的旧 manifest 不能混用；本次不提供启动器，也不自行扩大评分或出网授权。

部署时仍需精确绑定相应新计划和 provider 的 scope，封存新 manifest，并按原评测协议运行必要的 gold/empty 控制。特别是 TLS provider 的任务白名单、直连范围和字节/连接限额继续由独立授权约束；本模块不能替代这些门，也不开放生成演员外网。

原始 stdout/stderr 最多各记录 64 KiB 前缀，另记完整字节数和 SHA256；超限失败，不悄悄截断后接受。空输出、重复 JSON 帧、重复键、非法 CPU/namespace 类型均拒绝。边界观察成功本身也不等于资源检查成功：后续仍比对精确四核和四类 namespace 与宿主不同。

## 必要 CPU 控制

命令：`.venv/bin/python -m pytest -q tests/test_grading_repairs_v097.py`。

8 项通过，耗时 0.14 秒；对应源码和测试 Ruff 通过。覆盖：

- 模拟解释器缺 `sched_getaffinity` 时，真实读取只读 `/proc`，所得 CPU 集与当前解释器实际内核 affinity 相同；没有运行真实 Python 2 容器。
- 噪声帧、缺帧、多帧、重复键、非法值、非零退出，以及异常原输出留存。
- 实际新 `ObservedContainer.start` 路径保留基线、CPU 和 namespace 检查，CPU/namespace 负例均拒绝。
- 实际新 `_score` 私有回调，在模拟官方清理前读取 CA；CA 读取失败时仍清理、保留异常，旧全局绑定不变。

第一遍控制有 1 项 fixture 失败：测试误给两核，原四核校验正确拒绝；仅将 fixture 改为四核后复验通过。没有为了通过测试放宽生产规则。

## 1675 / 5530：保留为独立评分问题

| 原槽 | 已核实的失败链 | 后续修复方案；本次未实施 |
| --- | --- | --- |
| 1675，Sphinx-11510 REF | 官方 eval 的 `pip install -e .[test]` 尝试安装 `flit_core>=3.7`，离线 DNS 失败。随后一次 `git checkout <base> <全部测试路径>` 混入 4 个基线不存在的新文件，命令失败；候选实际修改过 `tests/test_directive_other.py`，其原内容未恢复，官方 test patch 应用失败 | 首先审计并封存所需构建依赖及离线安装闭包，仍保持评分容器无外网。测试复位应独立修订为按官方 test patch 的 preimage/新增/删除/重命名关系复位，保证官方测试内容与原设计一致；不更改原候选，不跳过失败测试，不把本次未知填成正常失败 |
| 5530，Astropy-7336 REF | 官方测试补丁含从 `py3_test_quantity_annotations.py` 到 `test_quantity_annotations.py` 的重命名。后者基线不存在，checkout 整批失败；候选实际修改过前者，未复位后官方补丁无法应用 | 需同一明确的测试复位修订，处理重命名前后路径。应以原基线与原官方测试补丁验证预期测试文件树，不能按模型输出临时选替代测试或改参考补丁 |

上表说明现有失败链，不证明修复上述环境问题后模型候选就会通过。依赖缺失与官方测试复位失败可能同时存在，需要分别保留状态。本次仅完成源码/日志核查与修复方案，没有改补丁、官方脚本或测试文件。

证据索引及源码引用见 [CPU 控制摘要](../../artifacts/software-benchmark-v097/grading-mechanism-control-r1/summary.json)。历史候选恢复保持独立：26 份已封存可补评，另 4 份缺最终控制器回执且桥接异常继续未知，详见 v095 报告。
