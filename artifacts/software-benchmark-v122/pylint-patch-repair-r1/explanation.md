# Pylint4604 未定原因修订

原解释“补丁应用失败”不正确。官方日志记录补丁干净应用，传入 patch.diff 与锁定候选完全相同；离线将同一补丁应用到原文件，结果也逐字等于锁定候选。

模型把 pylint/checkers/variables.py 从 2,152 行改成 32 行，删除 import re，却保留第 30 行 re.compile。正式 pytest 加载 conftest 时因此出现 NameError，测试未能收集。CPU 仅对同一字面量表达式复现缺少 re 绑定的错误，没有在宿主执行任务模块或测试。

官方评分器把“没有可解析测试输出”也编码为 patch_successfully_applied=false；原报告本身已经 resolved=false、infra_failure=false。旧外层因此误把确定的候选代码错误列为技术未知。

新 derived-resolution.json 仅修订测量分类为候选代码失败（resolved=false）；原 receipt、官方 report 和补丁均不改。无需修补模型答案、无需新 gold/empty 环境控制，也无需重新运行候选评分或模型。这是单独留档的证据裁定，不冒称新增官方评分。
