# v053：200 题主面板与 40 题重复诊断

Panel SHA-256：`8c756e1a8ac4b8dbd03c3a76651b103571c71a70ebe6baa3a80e7e069db7ad94`。本报告只读取既有回执，不执行模型或测试。

主结果固定使用 200 题第一次预定运行：成功 0，失败 0，未知 200；完成率 **null（尚有未知）**。
未知结果识别界限为 [0.0, 1.0]，该界限不是置信区间。
Wilson 95% 区间：None；仓库整簇 bootstrap 95% 区间：None。
Wilson 使用独立 Bernoulli 工作假设；整簇 bootstrap 保留任务归属，只有 20 个仓库簇，区间覆盖可能不理想。两者均不支持 SWE-smith 自然总体或 SWE-bench Verified 外推。

## 预选 40 题的重复诊断

| 预定轮次 | 成功 | 失败 | 未知 | 40 题完成率 |
| --- | ---: | ---: | ---: | --- |
| 1 | 0 | 0 | 40 | null（尚有未知） |
| 2 | 0 | 0 | 40 | null（尚有未知） |
| 3 | 0 | 0 | 40 | null（尚有未知） |

三轮均已知任务的成功次数计数：{'0/3': 0, '1/3': 0, '2/3': 0, '3/3': 0}；三轮记录不完整任务 40，单独保留。
已观察到成功／失败翻转的任务 0；40 题翻转比例 null（尚有未知），识别界限 [0.0, 1.0]。
三次重复只是有限波动诊断，不认证稳定性；不把 pass@3 或 280 回合混合平均当作主完成率。

## 全部库存与实际费用

全部 280 回合状态：`{'not_started': 280}`。零模型资源等待尝试 0 次。
| 范围 | 已知实际 token | 完整已观测实际 token | 不确定预约 token |
| --- | ---: | --- | ---: |
| 主面板 200 | 0 | 0 | 0 |
| 额外重复 80 | 0 | 0 | 0 |
| 全部 280 | 0 | 0 | 0 |

预算上限 140,000,000 输入＋输出 token；预约不冒称实际消耗，环境准备、CPU 测试、GPU 驻留另计。未闭合库存的最终总费用仍为 null。
已知模型失败类型：`{}`。
技术未知回合：0；原因（可多标签）：`{}`。

## 仓库层级

| 仓库 | 主题数 | 成功 | 失败 | 未知 | 完成率 |
| --- | ---: | ---: | ---: | ---: | --- |
| Knio/dominate | 10 | 0 | 0 | 10 | null（尚有未知） |
| andialbrecht/sqlparse | 10 | 0 | 0 | 10 | null（尚有未知） |
| arrow-py/arrow | 10 | 0 | 0 | 10 | null（尚有未知） |
| burnash/gspread | 10 | 0 | 0 | 10 | null（尚有未知） |
| django/channels | 10 | 0 | 0 | 10 | null（尚有未知） |
| django/daphne | 10 | 0 | 0 | 10 | null（尚有未知） |
| graphql-python/graphene | 10 | 0 | 0 | 10 | null（尚有未知） |
| hukkin/tomli | 10 | 0 | 0 | 10 | null（尚有未知） |
| iterative/dvc | 10 | 0 | 0 | 10 | null（尚有未知） |
| john-kurkowski/tldextract | 10 | 0 | 0 | 10 | null（尚有未知） |
| joke2k/faker | 10 | 0 | 0 | 10 | null（尚有未知） |
| keleshev/schema | 10 | 0 | 0 | 10 | null（尚有未知） |
| kennethreitz/records | 10 | 0 | 0 | 10 | null（尚有未知） |
| mahmoud/boltons | 10 | 0 | 0 | 10 | null（尚有未知） |
| msiemens/tinydb | 10 | 0 | 0 | 10 | null（尚有未知） |
| pallets/jinja | 10 | 0 | 0 | 10 | null（尚有未知） |
| paramiko/paramiko | 10 | 0 | 0 | 10 | null（尚有未知） |
| pyasn1/pyasn1 | 10 | 0 | 0 | 10 | null（尚有未知） |
| r1chardj0n3s/parse | 10 | 0 | 0 | 10 | null（尚有未知） |
| seatgeek/thefuzz | 10 | 0 | 0 | 10 | null（尚有未知） |

完整机器报告保留 200 个任务及 280 个回合的状态、费用和所属仓库。未知不补零，不只对已闭合子集计算主完成率。
