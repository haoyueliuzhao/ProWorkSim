# 12 道历史代码失败题的 OSA 完整任务测试

12 题中 12 题完成生成。最终代码通过官方验收 3/12（25.0%），正确合法交付 3/12（25.0%）。每题从原始仓库、两名成员零历史开始，使用 DeepSeek Flash 非思考模式。本批仅运行 OSA。

| 任务 | 最终代码 | 正确交付 | OSA 决策 | 输入＋输出（万 token） | 费用（元） |
| --- | --- | --- | --- | ---: | ---: |
| astropy-14598 | 未通过 | 未通过 | 维持 | 499.55 | 8.22 |
| django-12663 | 未通过 | 未通过 | 维持 | 311.88 | 4.99 |
| matplotlib-23299 | 未通过 | 未通过 | 调整（verify） | 363.71 | 5.87 |
| pytest-10356 | 未通过 | 未通过 | 维持 | 398.40 | 6.49 |
| scikit-learn-25747 | 未通过 | 未通过 | 维持 | 499.17 | 8.23 |
| sphinx-9591 | 未通过 | 未通过 | 维持 | 295.99 | 4.74 |
| astropy-13236 | 未通过 | 未通过 | 维持 | 499.39 | 8.13 |
| django-12965 | 通过 | 通过 | 维持 | 380.40 | 6.13 |
| matplotlib-25960 | 未通过 | 未通过 | 维持 | 494.42 | 8.06 |
| pytest-5787 | 通过 | 通过 | 维持 | 496.66 | 8.20 |
| django-15916 | 通过 | 通过 | 维持 | 363.15 | 5.82 |
| pytest-5840 | 未通过 | 未通过 | 调整（verify） | 245.04 | 3.86 |

其中，在核查范围内仅找到失败评分的 11 题，本轮代码通过 2/11（18.2%）。

有 8 题得到项目的正式提交回执，其中 3 份提交通过官方验收。

| OSA 实际行为 | 题数 | 代码通过 | 正确交付 |
| --- | ---: | ---: | ---: |
| 实际改组 | 2 | 0 | 0 |
| 分工维持（含回退） | 10 | 3 | 3 |

分组取决于 OSA 当时的决定，两组数字仅描述本批实际行为。

## 官方验收未通过的题

| 题目 | 目标用例通过／失败 | 原有回归通过／失败 | 首个失败目标用例或回执 |
| --- | ---: | ---: | --- |
| astropy-14598 | 0／1 | 175／0 | astropy/io/fits/tests/test_header.py::TestHeaderFunctions::test_long_string_value_with_quotes |
| django-12663 | 0／1 | 135／0 | test_subquery_filter_by_lazy (expressions.tests.BasicExpressionsTests) |
| matplotlib-23299 | 0／1 | 192／0 | lib/matplotlib/tests/test_rcparams.py::test_no_backend_reset_rccontext |
| pytest-10356 | 0／1 | 79／0 | testing/test_mark.py::test_mark_mro |
| scikit-learn-25747 | 0／1 | 14／0 | sklearn/utils/tests/test_set_output.py::test_set_output_pandas_keep_index |
| sphinx-9591 | 0／1 | 44／0 | tests/test_domain_py.py::test_pyproperty |
| astropy-13236 | 0／2 | 644／0 | astropy/table/tests/test_mixin.py::test_ndarray_mixin[False] |
| matplotlib-25960 | 0／1 | 123／14 | lib/matplotlib/tests/test_figure.py::test_subfigures_wspace_hspace |
| pytest-5840 | 0／2 | 51／0 | testing/test_conftest.py::test_setinitial_conftest_subdirs[test] |

这 9 题中，9 题再次未通过至少一个与历史回执同名的目标用例；8 题通过了本次评分器执行的全部原有回归用例。

共 896 次已结算请求，输入 48,273,125、输出 204,364 token，平均每个已调用回合 403.98 万。含 12 次已记录的 OSA 决策，共 39,767 token。决策分布为 维持 10 次、调整 2 次。
本批结算 78.74 元；原账本累计 107.17 元，上限 150 元，扣除预约后可用 42.83 元。

三题的最近失败记录是历史准备阶段候选的官方评分，其余九题为后续执行分支或普通任务。本轮十二题均从原始仓库完整执行。Django-15916 在核查范围内另有通过记录，其余 11 题在该范围内未查到通过回执。历史回合与本次运行条件可不同，单组重新通过数不能用于估计 OSA 相对其他组织方式的提升。

[冻结方案与选题范围](v245-3-full-task-osa.md) · [原评分、运行决策与用量](../../artifacts/software-benchmark-v245-3/full-osa12-r1/results.json)
