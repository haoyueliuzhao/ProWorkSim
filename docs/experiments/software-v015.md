# v0.15 软件来源与父进程验收

固定 Marshmallow `c7b559a1fa3aba57ca6dba0ab336841c5038a782` 的真实源码已经进入世界，模型可实际读、改、执行测试并提交不可变版本。本报告记录 **CPU 规则见证、实际评分绕过及其修复**；真实模型结果单独报告，不从参考补丁推断模型能力或学习收益。

当前冻结协议为 `examples/software-v15/protocol.json` 的 `software-work-protocol-v0.15r1`。详细机制见 [设计](../design/software-maintenance-v015.md)，最终原始控制见 [software-v015-parent-acceptance-cpu.json](software-v015-parent-acceptance-cpu.json)，世界与动作保留于 `runs/software-v015-parent-acceptance-final/`。

## 确认并修复的评分绕过

静态审阅提出：可编辑的 fields.py 可以修改同进程 unittest 模块，而私有判断仍信任其返回。本轮通过实际工具和提交完整复现了该反例。只加入 `unittest.main = lambda ...: SimpleNamespace(result=SimpleNamespace(wasSuccessful=lambda: True))`，没有实现 strip_whitespace、没有适配消费者，即可让可见及旧私有驱动 stdout 都为空、正常结束，旧评分却为 **R=1**。完成 nonce 也存在，因而它不能证明任何业务断言真正执行。

错误结果保留在 [原反例](software-v015-unittest-bypass-original.json) 及 `runs/software-v015-unittest-bypass-original/`，没有被修订结果覆盖。此前 [5 项 CPU 控制](software-v015-cpu.json) 只证明原有限控制符合预期，没有覆盖这条绕过，不能继续作为可靠独立验收声明。

修订将 expected 与全部判据移到**可信父进程**。原 12 组性质展开成 29 个 API 查询，子进程只执行函数/字段/消费者/Schema 调用并返回值或异常。父进程逐项比较，不接受子进程的 `wasSuccessful()`、自报通过次数或私有 unittest 结论。隐藏 expected、分组、locator、比较逻辑没有传入执行模型代码的进程。源码定位使用实际对象 JSON 路径，符号另列。

这项修订发生在真实模型软件筛选之前，重新冻结协议。旧协议存档 [software-v015-protocol-before-parent-acceptance.json](software-v015-protocol-before-parent-acceptance.json)，新协议记录 supersedes SHA 及修改原因。原私有 unittest 文件保留为历史复现材料，新评分不再执行它。

## 最终控制结果

| 控制 | 可见驱动结果 | 父进程 API 检查 | 最终 R | 含义 |
|---|---|---:|---:|---|
| 原源码、原消费者 | 失败 | 6/29 | 0 | 原始公开源码不满足新模拟需求 |
| 规则参考补丁 | 声称通过 | 29/29 | 1 | 真实读取、编辑、执行、提交路径可运行 |
| 只去 ASCII 空格的缺陷补丁 | 声称通过 | 24/29 | 0 | 不能用公开测试绿灯代替完整合同 |
| 正确测试后又改源码再提交 | 声称通过但引用旧版 | 29/29 | 0 | 新提交不能借旧测试报告验收 |
| 正确提交后工作区被改坏 | 固定提交报告声称通过 | 29/29 | 1 | 使用提交快照，不偷读当前工作区 |
| monkeypatch unittest.main、未实现需求 | 空 stdout、声称通过 | 6/29 | 0 | 子进程跳过 unittest 已不能伪造正确性 |

可见测试仍原样执行并记录实际输出，其成功声明不再称为独立通过。父进程验收的完整 29 个请求、返回、expected、locator 和判断均在私有结果中保存，评估结束后用于审计；不回流到模型当步对话。

八个实际操作系统探针分别尝试读取宿主 canary、读取 `/etc/passwd`、读取 `/proc/self/environ`、写源码目录、写宿主 canary、创建 symlink、联网、开启子进程，均得到 EPERM/EACCES；canary 未变。提前零退出没有驱动完成标记；这个标记只用于识别不完整执行，不作为测试正确性的替代。

必要回归 `tests/test_software_maintenance_v015.py` **5 项通过**，覆盖不可变/撤回提交、部分读取、私有资产和路径/命令边界、真实 OS 拒绝、收集器提前结束不代提交，以及同进程 unittest 绕过的父进程拒绝。新增模块/脚本 Ruff 通过。最终 CPU **6 项控制符合事前期望**。这些不是模型 episode；未导出为训练样本，没有参数更新。完整上游 pytest 目录已按原字节归档，但没有运行完整上游回归，29 项检查只覆盖本有限新需求。

## 保留的环境开发记录

`software-v015-devcase1` 首次包安装因 provenance 类型不在核心枚举被拒；`devcase2` 发现 unittest 误把 driver.json 当命令参数，修订 argv 和主模块绑定后 `devcase3` 才测得原源码真实失败，`devcase4` 测得参考补丁通过。父进程验收首次控制 `software-v015-parent-acceptance-controls` 暴露字典键顺序导致错误拒绝，改为父进程规范化、保留 JSON 类型的比较；后续控制目录均独立保留。它们是环境构建记录，不计入模型能力分母。

有限输入检查不能证明任意未来调用或零预训练污染。Marshmallow 本轮用作开发来源，不能同时宣称为未参与选型的独立来源泛化测试。操作系统隔离有效性、来源准入、工作正确性、模型表现和参数学习收益仍分别表述。
