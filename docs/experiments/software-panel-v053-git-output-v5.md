# v053 准备修订 v5：分离 Git 警告与树身份

日期：2026-10-20。此次修订只处理环境准备期间机器输出的读取错误，不改变官方镜像、缺陷补丁、测试命令、资源配额、评分规则或模型参数。

## v4 停止证据

`artifacts/software-panel-v053/environment-admission-v4.json` 记录：

| 状态 | 仓库数 |
| --- | --- |
| 全部十题准入 | 10 |
| 来源资格不满足 | 6 |
| 公共故障后保持未决 | 8 |

已经写入 167 份任务资格：149 true、18 false；这些部分完成的任务不等于冻结主面板。汇总明确 `paused_common_system_fault=true`、`ready_to_freeze=false`、`model_runs_started=0`。已准入十仓库只提供 100 个整仓合格任务，未达到要求的二十仓库／200 题。

原始公共故障发生于 `kennethreitz/records` 的首个预锁任务 `kennethreitz__records.5941ab27.lm_rewrite__9giocolr`。该镜像基线 B 包含安装生成的 `records.egg-info/`，因此 B 与原 Git 提交树 T 不同。计算官方任务分支的辅助安装差异投影时，Git 成功应用差异，但产生四条空白警告。

旧执行通道使用 `demux=False`，将标准错误和标准输出合并。`projected_task_trees` 又将整段合并输出的 `.strip()` 当作树 SHA。实际字符串包含警告和最后的有效树：

```text
524eca13506d1e21429df9c63daa42977c4b2bef
```

后续 `git read-tree` 因收到“警告文字＋SHA”而以状态 128 退出。这里没有证据表明补丁应用失败、镜像来源失效或模型产生错误。其余七个仓库因共享停止事件保持未决；不能把它们作为来源排除。

故障回执：

```text
runs/software-panel-v053/environments-v4/repositories/kennethreitz__records.5941ab27/common-system-fault-850e81781c1645f0af7d4ca5e6ffe8b6.json
SHA-256 706f850f56fe8bf6c2535036c7844e6e7cf6462728155d8f67cdf1c7706d0f67
```

对应未完成尝试保存在：

```text
runs/software-panel-v053/environments-v4/tasks/kennethreitz__records.5941ab27.lm_rewrite__9giocolr/bug/attempt-638de45098724820924f2fa0366ed46c/exception.json
```

## 最小修改

只在辅助 Git 投影调用中请求分离输出流：

- 标准输出必须精确解析为一个 40 位小写十六进制 Git tree SHA，否则仍作为公共身份故障暂停。
- 标准错误单独保存在 `projection_stderr`，警告不进入 Git 对象名称。
- 不添加 `--whitespace=fix`，不改补丁空白，也不隐藏警告。
- 其他终端和官方测试调用保留原输出方式。

Git 命令本身、树投影算法、隐藏 F2P 规则、gold 回到 B 的要求均未变化。新增字段只是诊断证据，不是科学 contract 参数。

## 唯一必要回归

新增一个实际运行 Git 的 CPU 回归：在临时仓库中构造带尾随空白及末尾空行的安装差异，让 `git apply --cached` 真实产生警告。控制确认警告确实出现在标准错误中，解析出的树仍为有效 40 位 SHA，投影树保留原始空白字节和 bug 实现，actor 树仍删除指定隐藏测试，原工作树不被投影过程改写。

该单项结果为 `1 passed, 19 deselected`，两个修改文件的限定 Ruff 通过。没有重跑既有测试套件、官方资格测试或模型回合。

## 既有结果复用边界

v5 使用独立准备目录，并通过指向旧不可变证据的文件链接复用已经完成的验证。该修正不改变旧成功结果的语义：

1. B=T 的任务不进入安装差异应用，原树身份与验证过程不受此次输出分离影响。
2. B≠T 且 v4 已完成的任务，原投影结果已经被后续 Git 命令接受，并通过重建 bug／隐藏树对照及 gold 返回 B 的检查。新的输出读取只移除树名称中不应出现的诊断文本，不改变这些树。
3. 官方源码／parser、image ID、C／T／B、任务数据、contract、资源及缓存政策保持一致时，已完成 clean／bug／gold 和资格回执无需重跑。源引用仍指向原始字节，不能改写旧回执以伪装为新运行。
4. 缺少 `completed.json` 或未成功完成的尝试不能当作完成证据复用。`records` 原公共故障及所有未决记录保留；后续新尝试使用独立路径，不覆盖它们。

复用避免重复 CPU 验证，不增加独立任务数，不改变预锁抽样，不把未知填为模型失败。v5 是否最终形成 200 题面板，仍取决于后续真实资格结果；本文不预先宣称成功。
