# v053：官方 harness 依赖与两条解释器路径

日期：2026-10-20。本次是正式模型运行前的依赖适配与 CPU 导入核验，没有模型加载、tokenizer 实例化／编码、GPU 上下文初始化或测试节点执行。

## 官方版本适配

固定 SWE-smith 源码为 `9b74ac08118a85c39c356802f7961893af73e07f`。初装的 `swebench==5.0.2` 与该源码不兼容：5.x 已移除源码所需的 `harness.constants.DOCKER_USER`、`DOCKER_WORKDIR`、`KEY_INSTANCE_ID`，并移动了 `harness.dockerfiles` 接口。仅补上最初报缺的 `datasets` 无法解决这项接口差异。

在专用 `runs/software-panel-v053/harness-venv/` 内，将 SWE-bench 固定为仍提供所需官方接口的最新 4.x 发布版 **4.1.0**。使用官方 PyPI wheel，SHA-256 为 `1243776f720047cc9e20a427f7a52b75c13a07abda6154fb60fe77f82ec8af57`。没有修改 SWE-smith／SWE-bench 源码，没有用兼容 shim 替换官方解析或评分，也没有修改 shared resident 包。

官方 harness 的 eager import 同时需要 `datasets` 和 `modal` 及其运行依赖。本轮复用已有下载缓存，只补齐缺失项；较大 PyArrow／pandas wheel 从官方 PyPI 并行分段下载，按发布 SHA 合并核验后安装。`datasets==5.1.0` 要求 `fsspec<=2026.7.0`，因此只在专用 harness 环境内固定 `fsspec==2026.7.0`，覆盖该环境可见的共享版本；shared resident 本身不改。

关键版本如下，完整清单不在正文展开：

| 官方 profile 合同记录的依赖 | 固定版本 |
| --- | --- |
| swebench | 4.1.0 |
| docker | 7.2.0 |
| ghapi | 1.1.1 |
| python-dotenv | 1.2.3 |
| unidiff | 1.0.1 |

其余导入所需的大包为 `datasets==5.1.0`、`modal==1.6.2`、`pyarrow==26.0.0`、`pandas==3.0.6`。本地实际安装 28 个包，完整有效环境 freeze 为 197 行，包含经原有 `.pth` 读取的 shared resident 包。未安装不参与当前导入／评分的 `pre-commit` 开发工具；本记录不宣称全局 `pip check` 已通过。

专用环境中的实际 `from swesmith.profiles import registry` 成功，注册 1,666 个 profile。初装失败、5.0.2 卸载、4.1.0 安装及完整来源记录均保留在该环境的 `bootstrap/`：

- `official-import-receipt.json`：SHA `593d6fa376249072fc1555367ab3af0869d47502cb5819b27084ad97cb7d9552`。
- `local-package-pins.txt`、`effective-pip-freeze.txt`：本地包与完整有效环境的版本记录。
- `download-receipt.json`、`swebench-compatible-wheel.json`、`pip-install-report.json`：官方 wheel URL、SHA 和安装记录。
- `installation-steps.json` 及对应日志：实际卸载／安装命令、退出码。

## 准入解释器与正式 worker 的实际核对

在私有 CPU launcher 内，用同一个首候选的原始任务行实际调用 `profile_contract`：

1. 准入路径使用 `harness-venv/bin/python`，项目 `src` 和项目根目录进入 `PYTHONPATH`。
2. 正式 worker 路径使用原 `runs/v016-sdk/resident-venv/bin/python`，`PYTHONPATH` 按顺序为项目 `src`、项目根目录、`runs/v030-runtime-deps`、专用 harness 的 `lib/python3.12/site-packages`。

两者都设置 `PYTHON_DOTENV_DISABLED=1`、`PYTHONDONTWRITEBYTECODE=1`，经过 `run-cpu.sh --write-project` 进入当前服务器的私有运行时。两条路径均使用 Python 3.12.3。

结果：首候选身份、完整官方 profile 合同、`harness_dependency_versions`、`oracle_sources` **逐字段完全相同**。这里比较的是实际导入来源和实际返回的合同，不是只比较版本字符串。

| 评分来源模块 | 两条路径相同的 SHA-256 |
| --- | --- |
| `swesmith.profiles.base` | `144946dec5b5d1d41573f2b86fad459709d9fc9913d3cfc57cf897010e17c2fe` |
| `swesmith.harness.grading` | `1814fa6a459cc45dfb603eafc10a4a8831332280b3b7ec1bc7d3a1bfb5a1be0c` |
| `swesmith.constants` | `5e011a8f6472935b15f5898ef8671484f17c2f086ec443d04b294c7e479ec68f` |
| `swebench.harness.grading` | `88fc500ebaf692a53457149cec24dcf82dfa2d48f98021a894a087d275f61df4` |
| `swebench.harness.constants` | `c12fe2671fd8b7d8af8f5c711fceb2ca684254e2c1b4cde448422a44b8d04e35` |

两条路径也实际导入了 `torch`、`transformers` 和 `transformers.models.auto.tokenization_auto`：Torch 为 `2.6.0+cu124`，Transformers 为 `5.17.0`，AutoTokenizer 定义可用，CUDA 始终未初始化。这里只读取模块元数据，没有调用 `from_pretrained`，不代表模型推理或 tokenizer 容量验证通过。

额外的首次“所有数值模块元数据字典字面相等”断言为 false：准入环境的旧 `.pth` 经 `/data1/` 找到 resident，worker 经 `/data0/` 找到 resident，模块路径字符串不同。版本、源码 SHA-256、文件长度及其余数值元数据相同。该额外检查原件保存在 `comparison-strict-initial-failure.json`，没有改写为 true。请求核对的 `oracle_sources` 与完整 profile 合同在不归一化路径的情况下即完全一致，因此没有为这项额外路径差异修改环境。

最终比较回执为 `runs/software-panel-v053/harness-venv/bootstrap/qualification-worker-identity-comparison.json`，SHA-256：

`32a082bbc289b2eafbe6864869251524cb28dbc2132ab95bc818caf0ef1601ca`

回执绑定两条原始执行记录 `qualification-runtime-identity.json` 与 `formal_worker-runtime-identity.json`、探测脚本 SHA、原始 task／inventory／backend config、模块来源及首次额外断言 false。此次结果仅证明上述实际依赖与官方合同一致，不替代 200 题环境准入、正式模型运行或最终评分。
