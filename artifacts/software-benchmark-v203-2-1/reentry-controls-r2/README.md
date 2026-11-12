# v203.2.1 r2 零调用 operational admission 恢复 CPU 控制

仅运行 `tests/test_passive_reentry_v203_2_1_r2.py`，9 项通过，0.24 秒。所有账本、计划、原结果、清理回执和预算初始化输出均位于 pytest 临时目录。scope、host、reference/load、资源准入和 launcher 均使用本测试提供的 fake；reference 还显式拒绝读取临时目录以外的文件。没有访问或修改真实 API 账本，没有启动服务、Docker、模型或原 Harness。

被测入口为新的 `tools/activate_passive_pilot_v203_2_1_r2.py`。没有修改旧冻结运行源码；测试不修改激活器实现。

已覆盖：

- 首两条 admission 均 closed、requests 为空、原 slot 精确匹配且各自 quiescence 与 coordinator release 有效时，仅移除指定两条 operational admission，并保存原状态、原结果及清理回执的完整引用证据；第三条无关 admission 保留。
- requests 表已有任意一条记录即拒绝。本控制使用 settled 样本，检查账本逻辑内容和文件字节均未改变，也未调用预算初始化或 launcher。
- 错误 slot、不满足清理条件的 quiescence、把另一题的完整 quiescence 引用换到本题，均在 mutation 前拒绝。
- 上一 coordinator reservation 没有明确 released 时拒绝。
- 恢复记录存在且原证据完全相同时，重复运行不改变 SQLite 证据或时间。改变原结果引用后拒绝，不把“admission 已删除”单独视为可恢复依据。
- 第二条 admission 尚未 closed 时，第一条已开始的恢复变更随同事务回滚；表创建和其他行也不留下半完成状态。
- admission 缺失且没有相同历史恢复证据时拒绝。

幂等控制中的两次 launcher 调用均为 fake，且不创建 execution-started marker；它仅验证账本恢复的幂等分支，不表示可以重启已经真实启动的 coordinator。

测试命令：

```text
.venv/bin/python -m pytest -q tests/test_passive_reentry_v203_2_1_r2.py --junitxml=artifacts/software-benchmark-v203-2-1/reentry-controls-r2/pytest-junit.xml
```

JUnit 与源码哈希见同目录 summary.json。未运行大套件或真实恢复动作。
