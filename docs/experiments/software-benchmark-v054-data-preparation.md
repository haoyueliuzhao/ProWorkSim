# v0.5.4：完整 Verified 500 题数据准备记录

记录日期：2026-10-20（Asia/Shanghai）。本次属于用户授权的数据与环境准备，正式模型运行授权仍为 false。

## 1. 已完成的事实

固定 SWE-bench Verified `default/test` 数据已于 **2026-10-20 22:09:00（UTC+8）**从 ModelScope 国内入口直连下载成功。接收的完整文件为 6,304,616 bytes，SHA256 与此前核实的官方固定版本完全一致。CPU 准备程序已经读取完整文件，物化全部 500 个不同任务、500 个不同镜像引用及 REF/MATCH/PROJECT 共 1500 个预定运行槽。

没有替换数据版本，没有抽取环境较容易的子集，没有改变题目或按模型结果选题。所有槽均为 `planned_not_authorized`、`execution_authorized=false`、`model_attempts=0`；没有加载模型或使用 GPU。本记录只证明数据和计划清单准备完成，不证明 500 个实际容器已经全部可用。

## 2. 国内来源与内容身份

| 项目 | 已核实值 |
| --- | --- |
| 原始数据集 | `SWE-bench/SWE-bench_Verified` |
| 原始固定 revision | `78f471bf655a3137b2e8a75af1501690ec009ec3` |
| 原始路径 | `data/test-00000-of-00001.parquet` |
| 文件大小 | 6,304,616 bytes |
| SHA256 | `030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25` |
| ModelScope 文件 revision | `3cec2c43354183c2bcb57d455ea4d3e32f8f0b90` |
| 入口 | `www.modelscope.cn` |
| 实际数据交付域 | `cdn-lfs-cn-1.modelscope.cn` |
| 数据 payload | 6,304,616 bytes，一次完整传输 |
| 代理、原站 fallback | 均未使用 |

此前 ModelScope 页面摘要显示 2.10MB、schema 描述较旧，但这不足以判定实际文件版本。本次使用数据集正确的 `repo/tree` API，取得完整文件项的 `Revision`、`Size` 和 `Sha256`，三者确认后才下载。ModelScope 文件 revision 与 Hugging Face Git revision 不同；两个平台的文件字节长度及 SHA256 完全相同，建立的是内容一致性证据，不声称两个 Git 提交身份相同。

来源元数据端点：

```text
https://www.modelscope.cn/api/v1/datasets/SWE-bench/SWE-bench_Verified/repo/tree?Revision=master&Recursive=true&PageNumber=1&PageSize=100
```

实际固定下载入口：

```text
https://www.modelscope.cn/api/v1/datasets/SWE-bench/SWE-bench_Verified/repo?Revision=3cec2c43354183c2bcb57d455ea4d3e32f8f0b90&FilePath=data%2Ftest-00000-of-00001.parquet
```

下载继续使用既有 `tools/domestic_asset_download.py`，显式 `ProxyHandler({})`，没有扩大允许域，也没有放行 `cas-bridge.xethub.hf.co`。下载日志保留此前 hf-mirror 的拒绝记录和这次成功记录；签名查询参数已脱敏。新来源无需安装或调用 ModelScope SDK。

## 3. 全部任务与槽的固定方式

生成程序为 `tools/prepare_verified_data_v054.py`。它验证完整 500 行、ID 唯一、完整 base commit、官方镜像引用，以及当前 F2P/P2P 的列表类型。身份表只投影 `instance_id/repo/base_commit/image`，按 UTF-8 字节序排序，使用 UTF-8、JSON `sort_keys=true`、缩进 2 空格、末尾换行序列化。

| 产物 | 大小 | SHA256 |
| --- | ---: | --- |
| `artifacts/software-benchmark-v054/manifests/identities.json` | 117,823 bytes | `6e339ec6a6f6e22a0a04006cf14aa322645fbe33df1b4331e72d0c8e98dc0e69` |
| `artifacts/software-benchmark-v054/manifests/slots.json` | 548,528 bytes | `55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676` |
| `source/trusted-evaluation.json`，仅可信宿主 | 9,795,256 bytes | `bdd44ad7182b9cb9dd8d679fbdf119b4372e925f3c08c5a30178db818284cfbb` |
| `source/public-tasks.json`，公开输入投影 | 1,018,814 bytes | `65d130536d04fda752b6ab36534ec657a8cd9bb0243b36067a1eb45413245aaf` |

三个组使用相同 500 题。每题 seed 严格按既有公式固定：

```python
int.from_bytes(SHA256(UTF8("v054:202610200541:" + instance_id))[:8], "big") % 2**63
```

任务顺序使用 `random.Random(202610200542)` 打乱排序后的全部 ID；每题内按 `MATCH/PROJECT/REF` 的六种字典序排列循环。不存在重复诊断子集，旧 SWE-smith 的 40 题重复方案不再混入。`config/v054-verified-image-inventory.json` 从完整身份表派生，镜像 `image_name` 和 `tag` 来自原数据字段，用于新的官方 metadata 对照。

全部 500 题分布如下，保留官方测试集原始不均衡分布：

| 仓库 | 题数 |
| --- | ---: |
| astropy/astropy | 22 |
| django/django | 231 |
| matplotlib/matplotlib | 34 |
| mwaskom/seaborn | 2 |
| pallets/flask | 1 |
| psf/requests | 8 |
| pydata/xarray | 22 |
| pylint-dev/pylint | 10 |
| pytest-dev/pytest | 19 |
| scikit-learn/scikit-learn | 32 |
| sphinx-doc/sphinx | 44 |
| sympy/sympy | 75 |
| 合计 | 500 |

本次没有把旧方案的“至少 20 仓库、每仓库至多 10 题”施加到官方 Verified 全集；那会更换题集。

## 4. 隐藏材料边界

完整 parquet 和完整评分 JSON 位于 `artifacts/software-benchmark-v054/source/`。目录权限为 `0700`，原始 parquet 与生成的数据 JSON 为 `0600`，不进入 Git 发布。完整评分 JSON 保留全部 17 列，供固定官方评分器读取；没有把 `patch/test_patch/eval_script/log_parser/eval_type/F2P/P2P` 等列传给 Actor。

Actor 公开投影精确为 `instance_id/repo/base_commit/image/problem_statement`。没有附加 hints、参考补丁所涉及文件、隐藏测试名单或评分反馈。公开投影虽不含答案，仍由可信宿主按题选择、传入各组；不能把整个 source 目录挂载到 Actor。Unix 权限只是宿主文件管理措施，正式隔离仍要求容器挂载和执行工具权限满足方案。

生成器拒绝覆盖不同内容的已有冻结产物。文件权限已符合要求时不重复 chmod，以保留已有文件身份核验回执；传输和首次权限收紧后的内容核验各有明确用途，不做重复全文件扫描。实际 parquet 解析和 500/1500 完整性断言已在现有隔离 CPU Python 3.12 环境完成；脚本 Ruff 检查通过。

## 5. 就绪边界

本次闭合：固定数据国内交付、完整本地 500 题、纯身份清单、公开题文投影、可信评分记录、固定 seed 和 1500 槽、500 镜像引用输入。

本记录不替代：官方当前镜像 digest 核对、全部容器本地可用性、实际 Actor 初态隔离、评分环境和 REF/MATCH/PROJECT 数值／运行适配。镜像、评分和推理环境由本轮并行准备记录说明。没有因数据下载完成而启动模型评测。
