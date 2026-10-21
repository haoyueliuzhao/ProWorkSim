# v054 原生终态符号链接导出修订 r1

2026-10-21，REF slot83（`matplotlib__matplotlib-24970`）在 29 次模型调用、464,460 个完整结算 token 后正常结束。其 controller 因剩余预算不足以完整预留下一请求而闭合；所有 writer 已静默、resident 已正常 release，没有未知 token。候选导出随后被 `Symlinks must have relative repository-contained targets` 拒绝，原故障与唯一 candidate-claim 保留，尚未评分。

实际拒绝项是公开 Matplotlib 测试生成的三个链接：

| 路径 | 原始目标 |
|---|---|
| `result_images/test_colors/levels_and_colors-expected.png` | `/testbed/lib/matplotlib/tests/baseline_images/test_colors/levels_and_colors.png` |
| `result_images/test_colors/light_source_shading_topo-expected.png` | `/testbed/lib/matplotlib/tests/baseline_images/test_colors/light_source_shading_topo.png` |
| `result_images/test_colors/boundarynorm_and_colorbar-expected.png` | `/testbed/lib/matplotlib/tests/baseline_images/test_colors/boundarynorm_and_colorbar.png` |

该终态公开源码 `lib/matplotlib/testing/decorators.py:202` 使用 `os.symlink(orig_expected_path, expected_fname)`；`.gitignore:83` 包含 `result_images`。原 native RPC transcript 的请求 19、20、21 调用了公开 `test_colors.py` 的 pytest 入口。这里记录 gitignore 仅解释产物来源，不据此过滤候选。

修订新增独立 `software_benchmark_native_artifact_v054.py`，只接入 REF/MATCH 在生成完全结束后的原生候选捕获和标准 Git patch 导出。路径名继续要求规范仓库相对路径；普通文件继续使用 `O_NOFOLLOW`，链接只通过字节形式 `readlink` 取得目标，作为 Git `120000` 模式 blob 编码。绝对、悬空、仓外和非 UTF-8 目标均按原字节保存；不解析、不读取目标，也不把链接重新写成相对路径。非 UTF-8 目标仅在 JSON 包中使用显式 base64 编码，Git blob 保持原始字节。

PROJECT 的 provider、读写路径约束、`repository_sources_v054.py` 和共用受管 candidate exporter 未改。新的 native artifact 使用独立 manifest protocol，不作为可写 PROJECT source。原官方评分器仍收到标准 Git patch；没有更换评分标准、修改生成条件或添加模型反馈。

新的唯一 CPU 控制通过（0.15 秒）：绝对/悬空/仓外目录/非 UTF-8 目标原字节、原相对链接、目标未打开、原工作树未改变、gitignored 产物保留、bare-index 往返和普通 `git apply --binary` 工作树往返均通过；同一候选仍被 PROJECT 原 validator 拒绝。此控制没有模型、GPU、Docker或官方任务评分调用。它证明导出与应用编码，不代表 slot83 或任何正式题修复成功。

旧 `native_closure` 已原字节保存至 `artifacts/software-benchmark-v054/runner/revisions/r9/native-export-source-supplement/`；主索引由统一封源流程补入。本补丁只提供导出修复。对 slot83 的行政闭合必须继续引用原 claim、原终态和原配置，保留旧故障，不重新生成、不删产物、不修改候选内容。
