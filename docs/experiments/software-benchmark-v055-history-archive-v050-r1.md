# 旧 v050 历史 JSON 的无损去重归档

## 实际结果

本次仅归档 `runs/software-learning-v050-resume-r1` 至 `r6`，以及 `r6-restored` 下的 `entries.json` 与 `pretraining-admission.json`，共 14 个旧文件。没有扩大到初筛得到的其他约 70 GiB 历史文本，也没有处理模型、密钥、当前 v054/v055 轨迹或评测产物。

14 个原文件分别具有不同 inode，`nlink=1`，实际分配空间合计 12,322,562,048 bytes。逐文件全流 SHA-256 证明它们分为两个精确重复组，各有 7 个路径：

| 内容组 | 单份原字节数 | 原 SHA-256 | gzip 对象字节数 |
| --- | ---: | --- | ---: |
| entries.json | 1,491,995,552 | `ea5399c0b568633451e6f7a4343547514a98fa2a432d93b5af5d99dab8c0640b` | 146,034,702 |
| pretraining-admission.json | 268,361,556 | `3fcf9e0501bc13a0b73cedbd3efba79787fe985c2cb0c6140f202248b3eded45` | 19,794,036 |

两个内容寻址 gzip 对象实际分配 165,838,848 bytes。扣除这两个对象后，净回收 payload 空间为 **12,156,723,200 bytes，即 11.3218 GiB**；少量索引和审计文件另外占盘。这个数字根据文件分配空间计算，不能与并发实验期间的整盘 free 差值混同。

14/14 路径已归档，失败数为 0。原 supervisor 状态完整保留：r1 至 r6 为 `closed_with_unknowns`，r6-restored 为 `complete`。归档不把未知结果改成成功，也不重新计算历史成绩。

## 引用排除、内容身份与执行边界

当前 host、计划、bindings、kernel 与 source 元数据引用闭包去重检查了 4,192 个 JSON 元数据文件，发现 16,744 个显式 ref 路径；没有命中这批旧 v050 候选根路径。模型/actor/任务 payload、项目外路径未读取；另六个超过 16 MiB 的引用均为当前评测的代码树或候选 bundle，也没有读取其正文。完整路径审计保存在运行目录，提交的小型摘要明确记录这些排除范围。

在同 UID 的可观察进程中没有发现候选文件 fd 或候选根路径命令；部分 `/proc` 条目不可观察，审计没有把这一检查表述为对其他用户进程的普遍证明。旧 supervisor 的结束记录及其 SHA 同时进入固定 allowlist 计划。

原 14 个文件的身份、长度、分配大小、mtime、mode、uid/gid 和 SHA 保存在 `runs/history-archive-v050-r1/plan.json`。每个精确内容组只压缩一次，采用 gzip level 1，随后完整解压读取一次，核对原始字节数与 SHA-256。验证通过后才发布归档对象，再为每个原路径写入 `.archive.json` 侧车并回收 raw。执行中任何失败会保留独立失败记录；不自动重复不明确的历史归档操作。

流式指纹耗时 21.496 秒，正式归档耗时 21.714 秒。两步都通过独立 systemd 单元限制为 CPUQuota=200%、MemoryMax=2 GiB、IOWeight=10、Nice=10、IOSchedulingClass=idle。归档只使用本地文件，没有网络传输或模型调用。

相比为精确重复原文件建立硬链接，本方案进一步压缩两份唯一内容，并避免把历史路径变成共享的可写别名。代价是历史工具如果直接打开原 raw 路径，需要先执行显式恢复；这不是对历史 SHA 或结果记录的静默改写。

## 查找与显式恢复

归档对象位于：

```
runs/history-archive-v050-r1/objects/<原SHA-256>.json.gz
```

每个原路径旁的 `<原文件名>.archive.json` 指向中央 plan 和已完整验证的对象。原 SHA reference 保留原含义；需要按原路径再次使用旧校验器时，应先恢复原字节到该路径。

恢复工具是 `tools/archive_v050_history_r1.py`。默认恢复到独立的新目录，按原项目相对路径布局；下面的例子只恢复一个所需文件，避免无意重新占用全部 11.476 GiB：

```bash
python3 tools/archive_v050_history_r1.py restore \
  --plan runs/history-archive-v050-r1/plan.json \
  --sha256 86911b1ff74ddea4d032c0d2563bfd4102e3ba9e048a6c54b18ae1acda48d037 \
  --path /data0/zhuxinrui/projects/ProWorkSim/runs/software-learning-v050-resume-r1/entries.json
```

默认输出为：

```
runs/history-archive-v050-r1/restored/runs/software-learning-v050-resume-r1/entries.json
```

可用 `--destination /另一个新目录` 指定恢复根目录。只有明确添加 `--original-paths` 才恢复到原路径；它与 `--destination` 互斥。两种模式都拒绝覆盖现有目标，解压时核对原 SHA 和长度，验证后以独占方式发布目标，并恢复记录的 mode 与 mtime。原 uid/gid 作为历史元数据留存，不声称跨用户恢复时会自动改变文件所有者。

省略 `--path` 将恢复 plan 中全部 14 个路径，即使多个路径共享同一个压缩对象。历史原路径 SHA 验证需要原路径恢复模式；默认新目录模式用于检查或分析，不更改历史引用。

## 必要控制与证据

一次小型临时 fixture 控制通过，真实历史文件改动为 0，覆盖同 SHA 共用一对象、验证后才回收 raw、原身份侧车、默认新目录恢复、拒绝覆盖、显式原路径恢复，以及解压回读不匹配时保留原件。实际归档中，每个唯一对象完整回读验证一次后即采用其证明，没有为了展示结果再恢复真实 raw 或重复全量哈希。

小型证据位于 `artifacts/software-benchmark-v055/history-archive-v050-r1/`，压缩数据本体仅保留本地运行目录，不提交到 Git。

- plan SHA：`86911b1ff74ddea4d032c0d2563bfd4102e3ba9e048a6c54b18ae1acda48d037`。
- result SHA：`6c26c038b87270447bf202f63edf0da0360d8b4731e4e0a331671aa5d8043789`。
- CPU 控制 SHA：`55fc39edb1daefa4bf0a91ce6ccb4c7990d53ba450c68c32e81fb31cd19dbaf2`。
