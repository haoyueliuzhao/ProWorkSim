# 旧实验文本第二批无损归档

本次针对用户要求继续压缩无用历史数据，固定处理候选261个旧实验文本；不包含当前v054/v055任务、模型权重、检查点、镜像、旧实验评分和监督器记录，也不重复上一批已归档的14个v050文件。

## 范围与状态

精确路径在 `artifacts/software-benchmark-v055/history-text-archive-r2/candidates.json`。固定清单的SHA-256为 `3543694f4a8f234bfea9716be7b1ccc87a1ee99b10c724d106641e935f2c9855`。选择不依据实验成绩：

- `software-learning-v050-resume-r1` 下117个大于1 MiB的 `runtime.json`、`experience.json`、`experience.jsonl`。
- `software-organization-v047` 下132个同类文件。
- v049/v050中12个大于100 MiB的 `entries.json` 或 `admission.json`。

261个路径互不重复。它们是可无损压缩的历史记录，不能作为可直接丢弃的无用文件。最终准入还要求对应历史supervisor为 `complete` 或 `closed_with_unknowns` 且有结束时间；保留原有结果及技术未知含义。任何当前引用、进程使用、历史结束证据不足或身份异常都会排除该文件并记录原因。

北京时间2026年10月22日23:53:59完成：**261/261路径归档且raw释放，排除0，失败0**。256个唯一内容组形成256个经过完整回读验证的gzip对象。原allocated合计14,628,708,352 bytes，保留压缩对象allocated合计1,537,060,864 bytes，净释放payload为 **13,091,647,488 bytes（12.192547 GiB）**。少量侧车、索引和收据未从这个payload净值扣除。此数来自实际文件分配量，不使用并发实验期间整盘free变化代替。

最终引用审计检查9,058个JSON元数据、30,407个不同路径引用，候选命中0；路径队列峰值15,658。10,410个模型/任务/历史payload引用和86个超过16 MiB的JSON按事前范围排除并记录；未因候选表现修改清单。当前同UID检查无候选使用，46个proc条目不可观察，保留这一可见性边界。

正式plan SHA为 `24d7048a03c3d9377f011e2b97df539d0a3fdc6e9ee259e80a20d5c998293c9f`，result SHA为 `b9eb5eb36dc6441f2a85f7d89d2c5b5791e0c277ed69744016870f0746fb4c64`。两步有限单元均正常退出，systemd管理器保留日志及请求的资源配置见小型证据 `completed-units.json`。成功后临时单元已卸载，完成时查询得到的默认属性不能冒充运行期资源实测。压缩正文保留在本地 `runs/history-text-archive-v055-r2/objects/`，不提交到Git。

## 当前依赖排除和静止范围

从当前Qwen bindings、kernel与资源修订、REF转接及三卷host，以及DeepSeek队列计划、active host、native solver和budget activation开始，遍历显式JSON元数据引用。只保留去重路径队列，不保留全部解析文档；不做全盘扫描。不读取模型、rootfs、任务工作区、公开任务正文或隐藏评价材料；大于16 MiB的元数据引用明确记录排除原因。

每个候选都与可达引用及目录级引用比较；完整审计写入本地 `runs/history-text-archive-v055-r2/current-reference-audit.json`。执行前再次确认队列的上述配置引用没有变化，不重复遍历全部图。当前同UID可观察命令和打开文件也检查候选使用。不可观察的 `/proc` 数量会保留，本证明不声称覆盖其他用户所有进程。

## 无损保证与恢复

新入口 `tools/archive_closed_history_text_v055_r2.py` 通过私有模块实例复用原 `archive_v050_history_r1.py` 的gzip level 1、内容寻址、完整解压SHA核验和逐路径回收实现，原r1源码、归档对象和计划不改。新入口和旧codec源码SHA、候选清单、监督器SHA、原文件设备/inode/nlink/字节数/allocated/mtime/mode/uid/gid及原SHA一起进入固定plan。

每个原文件只做一次准备指纹。相同SHA共用一个压缩对象；每个唯一对象编码时检查原文SHA与稳定身份，随后完整解压回读一次，核对原SHA与字节数。发布验证通过的对象后才写原路径旁的 `.archive.json` 并释放raw。原记录的SHA语义不变，历史校验器若要打开原raw路径，需要先显式恢复。

默认恢复到新的 `runs/history-text-archive-v055-r2/restored/`，不覆盖任何现有文件；可通过 `--path` 仅恢复一个文件，避免重建全批raw。`--original-paths` 才写回原位置，并且同样拒绝覆盖。恢复流再次核对原SHA和字节数，恢复mode和mtime；uid/gid作为原身份元数据保留，不声称在跨用户恢复时自动改变owner。

```
python3 tools/archive_closed_history_text_v055_r2.py restore \
  --plan runs/history-text-archive-v055-r2/plan.json \
  --sha256 24d7048a03c3d9377f011e2b97df539d0a3fdc6e9ee259e80a20d5c998293c9f \
  --path /data0/zhuxinrui/projects/ProWorkSim/runs/<固定候选原路径>
```

## 资源和必要控制

准备与执行均为独立有限systemd单元：CPUQuota=200%、MemoryMax=2 GiB、IOWeight=10、Nice=10、IOSchedulingClass=idle、无自动重启、最长1800秒。不重启或发送信号给实验队列、模型或任务单元。正式归档还要求当前可用空间覆盖本批最坏原始体积加128 GiB保留，不借用实验安全余量。

小型临时fixture验证固定261条唯一范围、不重复旧14条、r2恢复入口侧车、拒绝越界plan、默认新目录精确恢复、拒绝覆盖、旧r1源码未改变，以及引用队列只保存去重路径和准确记录命中。旧codec的压缩回读控制沿用，不额外恢复真实历史raw。

第一次准备尝试在引用图遍历时保留过多解析JSON，在独立2 GiB cgroup内因内存上限退出，未生成plan、未改动真实历史文件。该失败保存在 `runs/history-text-archive-v055-r2-failed-preparation-r1/failure.json`。随后将待处理队列改成去重路径，保持资源上限不变，以新准备单元执行；不把失败隐去，也不将其计入模型失败。
