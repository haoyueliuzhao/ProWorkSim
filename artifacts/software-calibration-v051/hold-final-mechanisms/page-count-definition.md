# HOLD 终态页计数定义

原机制摘要保持不变：`report.json`，SHA256 `7738b74f1c76beeba7a394206319d13055c2caec387f463b57bd877dc11a03c7`。本说明仅保存先前已查得的冻结定义，没有新增原件读取、测量、编码、测试或模型执行。

`actual_page_read_requests=32` 统计实际模型决定中的 `read_test_result` 动作。`verified_page_feedback_returns=79` 统计已验证的含页反馈条目，既包括 `run_tests` 自动附带的第一页，也包括显式读页返回。本批既有计数为 **47 个 `run_tests` 初始页 + 32 个显式读页条目 = 79 个已验证含页反馈条目**。

79 不是独立读页调用数、唯一页数，也不是同一反馈在后续多个模型输入中的重复呈现次数；不能写成“32 次读页调用产生79 个独立回包”。每条 verified 反馈只贡献一个 fragment，其 `actual_inputs` 列表不会再乘入该计数。语义理解和伙伴使用仍未分析。

定义来自共同快照 `0770d02f11bae4b33018c94be809f416c5fb91a2`：

- [software_organization_measurement_v050.py:843](/data1/zhuxinrui/projects/ProWorkSim/runs/software-holdout-v051-common/source/src/proworksim/software_organization_measurement_v050.py:843)：对各报告历史的 `verified_page_feedback_count` 求和；相邻表达式单独统计实际 `read_test_result` 动作。
- [measure_organization_projection_v046.py:623](/data1/zhuxinrui/projects/ProWorkSim/runs/software-holdout-v051-common/source/scripts/measure_organization_projection_v046.py:623)：`page_feedback` 只接受 `run_tests` / `read_test_result`；`run_tests` 返回必须为第0页。
- [measure_organization_projection_v046.py:728](/data1/zhuxinrui/projects/ProWorkSim/runs/software-holdout-v051-common/source/scripts/measure_organization_projection_v046.py:728)：`report_histories` 用 `len(fragments)` 计已验证含页反馈条目。

推荐表述：“32 次显式读页；79 条已验证含页反馈，其中47 条来自 `run_tests` 附带的初始页。此计数不表示唯一页数或语义使用。”
