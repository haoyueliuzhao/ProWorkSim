# v0.36 可选成员自测的完成证据与世界适配

本修订新增 `software_member_tests_v036.py` 和 `software_collaboration_v036.py`。它处理标准 `unittest.main()` 成功后以 `SystemExit(0)` 结束、因而未抵达旧外层完成标记的问题。旧 sandbox、v0.30/v0.35 成员自测实现、旧实验脚本、历史成员自测状态及历史 R 均不修改，也不重跑旧交付。

这仍是可选成员脚本的反馈协议，不是新的任务奖励或验收。`software_tasks_v036` 的保留训练根继续使用 v0.35 原合同、原公开检查和原任务私有验收；新世界仍要求当前版本已有实际测试和固定 patch 才受理提交，提交本身仍不是独立验收。

## 1. 新身份与复用边界

| 身份 | 值 |
|---|---|
| 世界版本 | `software-collaboration-v0.36` |
| 接口版本 | `purpose-isolated-autonomous-work-v0.36` |
| 对外测试反馈版本 | `structured-public-test-feedback-v0.36` |
| 成员脚本完成协议 | `member-script-completion-v0.36` |
| 公共反馈投影算法 | 原 `structured-public-test-feedback-v0.34` |

`case_spec` 和 `preparation.json` 绑定新反馈版本，以及成员协议的实现文件 SHA256、固定 driver SHA256。`member_test_specification()` 返回这些字段，供新 runtime 的 Γ 同时冻结；`port.observe()` 公开新的接口、反馈和成员测试版本。旧 case 的世界版本不能通过新 `validate_case`。

世界仍使用原有 O1 工具、团队预算、两份私有工作树、空执行任务表、固定版本和提交门。公共成功项摘要、失败业务内容、成员自测输出的投影算法不改；只在同一既有投影上标明新成员协议及新的外层反馈身份。底层 `software_context_v034` 不改写。本修订不会提供“新旧成功率之差仅由 Mapper 导致”的解释依据。

## 2. 判定规则

固定 driver 在原来的隔离执行进程中运行，没有修改 `software_sandbox.run_isolated`。它暂时包装并调用原标准库方法，记录：

1. `unittest.TestProgram.runTests` 对应的具体程序实例。
2. 原 `unittest.TextTestRunner.run` 是否正常返回，以及返回的真实 `unittest.TestResult` 对象。
3. 同次 runner 中原 `unittest.TestCase._callTestMethod` 是否实际进入并退出，避免把只有一个自行填入 `testsRun=1` 的空结果当成测试已运行。
4. 结果中的失败、异常、跳过和 unexpected-success 数量，以及原 `TestResult.wasSuccessful` 的判断。

仅当 `SystemExit` 的 code 是整数 0、异常来自原 `TestProgram.runTests` 的退出位置、对象身份绑定同一已完成 runner 和其 result、结果成功且至少一个测试方法实际执行，才在顶层识别这一次异常为 `verified_unittest_main_exit_zero`。driver 随后正常返回，让旧 sandbox 自己生成原完成标记。不是全局吞掉 `SystemExit(0)`，也不是把 stdout 中的 `OK` 当成权威结果。

普通自定义断言脚本必须正常返回。没有显式 unittest runner 的普通脚本仍按“脚本完成”判定，不自动发现测试，也不宣称运行了某个数量的断言。对显式标准 unittest 执行，新协议要求观察到非空真实执行和成功结果；零测试、仅跳过测试、或 `exit=False` 下返回的失败结果均不能据正常进程退出变成通过。

driver 输出带当次随机关联前缀的结构化完成记录。调用端还必须看到原 sandbox 的 `driver_completed=True`、进程返回码 0、唯一可解析的成员完成记录及其中的成功状态；缺记录、重复记录、不可解析记录或没有外层完成标记都不能通过。成员脚本的原输出和结构化观察保留在测试反馈中。

| 情形 | 新反馈语义 |
|---|---|
| 普通断言脚本正常返回 | `passed`，完成方式为普通脚本返回；不自动推断测试发现数量 |
| 标准 unittest 真实非空运行成功，`main()` 自身退出 0 | `passed`，有 runner/result/实际方法执行及外层完成证据 |
| unittest 失败并非零退出 | `failed` |
| unittest `exit=False` 返回，但结果失败 | `failed` |
| 普通异常或断言失败 | `failed` |
| 任意 `sys.exit(0)`，即使 stdout 写了“OK” | `failed` |
| 成功 unittest `exit=False` 返回后，又任意退出 0 | `failed`；之前的成功结果不能为后一次任意退出背书 |
| 标准 unittest 零测试或仅跳过测试 | `failed`，不能声称存在实际测试方法执行 |
| 自定义 runner 只返回伪造的成功计数 | 不获标准 runner 完成资格，不能接受其退出 0 |
| 返回码 0、外层完成标记存在，但缺成员完成记录 | `failed` |
| 空脚本、仅文档字符串或 `pass` | `untested`，不启动执行 |

标准 `unittest.main()` 的退出仍终止该成员脚本后续语句；修订没有继续执行本来位于退出点之后的代码。通过的是已观察到的 unittest 完成路径，不是对所有潜在后续语句的执行保证。

首版可核对范围是标准同步 unittest 路径；没有声称能够证明任意自定义测试框架、异步框架重写或敌意运行时篡改的完整执行。实际测试发现由成员脚本显式调用的 unittest 负责，本协议不额外自动发现测试。

## 3. 有限 CPU 控制

命令：

```bash
CUDA_VISIBLE_DEVICES='' \
PROWORKSIM_V036_MEMBER_CONTROL_RUN=runs/v036-controls/world/development-1 \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
.venv/bin/python -m pytest -q tests/test_software_member_tests_v036.py
```

本次首次执行结果为 **16 passed in 2.33s**，包含：

- 13 个新的实际隔离成员脚本案例：上述正常返回、成功／失败 unittest、异常、任意退出、成功后另一次退出、零测试、仅跳过和伪造 runner 反例。预期结果为 3 个通过、10 个失败，全部符合。
- 1 个注入缺少结构化完成证据的反例控制，没有实际执行成员脚本。
- 1 个空成员脚本明确 `untested` 的控制，没有启动隔离执行。
- 1 个新的 CPU 参考世界控制：两个私有副本及空任务表成立；保留训练根的完整原 source_contract 相同；新成员 unittest 成功退出被识别；既有公开摘要、完整原测试事件、投影幂等性和 operation-commit 绑定成立；测试前、固定前和后续编辑后的提交门保持。

实际隔离执行共 15 次：13 次独立成员脚本，加 CPU 世界内 1 次公开 driver 与 1 次成员脚本。世界只调用 1 次 `run_tests`；没有运行任务私有独立验收。它使用新建的明确参考程序，既不是历史模型提交的重演，也不是当前策略支持样本。

针对新增的两个实现模块和测试文件运行 Ruff，结果 `All checks passed!`。没有为本修订运行旧 15 份交付、全仓 pytest、真实模型、参数更新、SDK 脚本轨迹或 GPU。

控制原件在 `runs/v036-controls/world/development-1/`；统一命令、结果和源码指纹在 `runs/v036-controls/member-tests/checks.json`。这些 CPU 控制验证协议分支，不估计模型采用该接口后的业务成功率，也不作为贡献开发或独立确认结果。

## 4. 历史与后续实验边界

v0.35 中 stdout 显示成功而 `driver_completed=False` 的成员脚本继续保留原 `failed`。这里不将其重判，也不改变原完整验收或 R。新世界接口/反馈的变化须进入 v0.36 Γ，并对后续 B、G-raw、I-P 保持一致；该绑定由新 runtime 负责。新来源面板及 Mapper 的资格与本成员脚本控制分开记录。
