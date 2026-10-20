# v053 官方镜像依赖缓存适配 v4

日期：2026-10-20。本文记录正式模型运行前的 CPU 环境适配，不报告模型成绩。配合[环境说明](software-panel-v053-environment.md)及[镜像基线 v3 修订](software-panel-v053-mirror-baseline-v3.md)阅读。

## v3 中断的事实

pipeline-v3 已实际开始 clean／bug／gold 资格准备。最早 Pydantic 失败显示 5,438 项必要测试全部缺失，但原始日志没有进入 pytest：`uv run` 重建本地 Pydantic 时，需要 `hatchling` 和 `hatch-fancy-pypi-readme>=22.5.0`，随后尝试访问 PyPI，因容器 `network=none` 而 DNS 失败。

只读检查原始官方镜像发现，这两个构建依赖原本已存在于 uv 的索引、wheel 和解压缓存中，具体包含 hatchling `1.27.0`、hatch-fancy-pypi-readme `25.1.0`。旧适配代码却在源码初态清理时执行 `rm -rf /root/.cache`，删除了这些官方构建资源。固定官方测试包装没有这一步。因此这不是可以直接归为来源不可运行的证据，更不是模型失败。

诊断回执为 `runs/software-panel-v053/cache-diagnostic-v3/receipt.json`，SHA-256：

```text
e858b6101946a9319d842d5735caeeaffa7713eb418e0a48f3e72574f942bec4
```

根流程确认 v3 完全退出后才修改代码。停止记录为 `runs/software-panel-v053/v3-common-cache-fault.json`：76 份任务资格（64 true、12 false）、161 次阶段尝试、160 份阶段回执，正式模型调用为 0，尚未形成主面板。全部原始结果保留；不使用该公共适配错误导致的 false 跳过 Pydantic。已执行 CPU 测试与产生正式能力成绩是不同事件。

另一个同时检查的 Flake8 `pr_1848` 失败不具有相同原因：其 conda 环境已正确激活，clean／gold 均实际完成 464 项通过；bug 在收集阶段中断，没有产生 419 项必要节点的可确认失败状态。该事实符合本轮严格转移资格不能闭合的描述，不能通过补写节点状态使其通过。

## 修订范围与缓存内容

源码清理继续移除 `/testbed` 下旧 `.git` 历史、`__pycache__`、`.pyc`、`.pyo`、pytest 缓存和已知临时缺陷文件。停止整删 `/root/.cache`，保留不可变官方镜像提供的依赖缓存。

在本次控制的原始 Pydantic 镜像中，项目 editable wheel 的全部五个成员为：

```text
_pydantic.pth
pydantic-2.11.0a2.dist-info/METADATA
pydantic-2.11.0a2.dist-info/WHEEL
pydantic-2.11.0a2.dist-info/licenses/LICENSE
pydantic-2.11.0a2.dist-info/RECORD
```

`.pth` 内容仅为 `/testbed`；没有 `.py`、`.pyc`、`.pyo` 或 `.so` 实现。因此这份已检查的 editable wheel 不提供另一份正确实现。此结论限定于该镜像中实际检查的项目 wheel，不把其他任意缓存都断言为无源码。

另只读核对了固定前 24 个候选仓库的官方 profile 安装指令：除 Pydantic 外，目标项目均由本地 `pip install -e .` 或带 extras 的同类命令安装；fvcore 另外安装 torch／shapely 并删除一份测试。未见这些 profile 主动下载目标项目的远端 wheel／sdist 或执行目标 `pip wheel`。pip 文档说明 editable 构建 wheel 不持久缓存，直接本地目录构建的 wheel 也不跨安装调用缓存。[pip 构建接口](https://pip.pypa.io/en/latest/reference/build-system/)、[pip 缓存说明](https://pip.pypa.io/en/stable/topics/caching/)。

上述安装指令只解释为何不应由这一步产生目标项目的完整缓存副本，不能代替对所有历史镜像缓存的实际审计。本次没有开展全仓库缓存扫描，也不声称全池缓存均已审计；后续若出现目标源码副本的实际证据，再进行定向检查、清理并记录准备修订，不因假设重新删除全部依赖缓存。

内容检查回执为 `runs/software-panel-v053/cache-adaptation-v4/original-cache-audit.json`，SHA-256：

```text
258be0fdcdabcaa99d19d765576ab97ea4db26d3a6952bbab804bd01d1b20542
```

## 为什么仍需要 UV_OFFLINE

首先只保留缓存，维持原命令和 `network=none`，执行一次必要 clean 控制。结果仍在 pytest 启动前请求 PyPI，5,438 项必要测试观察数为 0。它被保存在 `runs/software-panel-v053/cache-adaptation-v4/result.json`，`passed=false`，clean 身份为：

```text
5f275522dc1dc4a29531569948ce7b7bd4c202c23b61be2783a1b7dcaf4009e4
```

该实际失败证明网络隔离和“解析器主动使用现存缓存”并非同一设置。随后固定容器环境 `UV_OFFLINE=true`，没有改写官方 `test_cmd`，没有安装或升级任何依赖。uv 官方说明该开关使其只使用本地缓存及本地文件；其缓存策略也会遵循 HTTP 缓存头。[uv 命令文档](https://docs.astral.sh/uv/reference/cli/)、[uv 缓存文档](https://docs.astral.sh/uv/concepts/cache/)。

原缓存具体为何在这次重建中请求重新获取元数据，没有另行追踪；不能把某一种缓存过期路径当作已经测得的事实。这里使用该开关的直接依据是上面的失败日志和下面的受控成功。

固定 contract 新增 `uv_offline=true` 及 `dependency_cache_policy=preserve-official-image-cache-offline-uv-clear-source-bytecode-v4`。缓存政策同时进入 clean 复用键。两个修订步骤使用不同的 clean 身份，先前失败不被覆盖。

## 必要验证与结果边界

新增一个 CPU 回归控制，实际创建旧 Git 对象、源码字节码、pytest 缓存、依赖 wheel 和 editable `.pth`，执行真实清理脚本后确认：旧历史及字节码消失，当前源码和依赖缓存字节不变。该项通过，未重复旧测试套件。

加入离线设置后，仅执行一次新的 Pydantic clean，继续使用原官方命令：

```text
/root/.local/bin/uv run pytest --disable-warnings --color=no --tb=no --verbose
```

结果：

| 观察 | 实际值 |
| --- | --- |
| 官方命令退出状态 | 0 |
| 原始 pytest 日志 | 5,810 passed、420 skipped、17 xfailed |
| 本题必要 F2P＋P2P | 5,438 |
| 实际观察到的必要节点 | 5,438 |
| 必要节点 PASSED／XFAIL | 5,438 |
| clean 控制整体 wall time | 33.887 秒 |
| 模型调用 | 0 |

全套日志中的 skipped 不在这道预选题的必要集合内；没有将它们改为通过。其他题仍需逐项核对自己的必要集合。此次成功只证明本题 clean 和该共享执行身份可运行，不等于 Pydantic 的十个任务全部完成 bug／gold 资格，更不等于正式 200 题评测完成。

控制结果：`runs/software-panel-v053/cache-adaptation-v4-offline/result.json`。完整 clean 回执 SHA-256：

```text
800c3a362f2160d6d8f46a98a0fd0b020013475e5660890b73489a00e9258191
```

成功 clean 身份为：

```text
fb8493156e5a0c3207f4718319dcc65e5edf5e2bfe1dd1bdfc8d13f1cc0fd7e9
```

该回执及 `completed.json` 已写入 `environments-v4/repositories/pydantic__pydantic.acb0f10f/clean/` 对应目录。新流程在相同固定身份下可直接复用此 clean，不需要重复运行；继续执行预锁任务的 bug／gold 和后续独立导出、评分控制。
