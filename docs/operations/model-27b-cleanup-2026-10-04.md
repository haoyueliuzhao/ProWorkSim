# 2026-10-04 旧 27B 模型清理

按用户“清理先前下载的 27b 模型”的明确授权，于北京时间 **2026-10-04 12:24:36** 清理旧 `Qwen/Qwen3.8-27B` 权重和专属下载缓存。当前 9B 基座、LoRA/checkpoint、正式实验轨迹、冻结源码及历史报告均保留。没有运行模型测试或修改训练配方。

## 删除范围与空间

模型目录：`runs/assets/models/Qwen3.8-27B-1d4bf0f2ff60`。固定来源 revision 为 `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`。本次只删除下列精确清单，没有递归删除整个模型根目录。

| 对象 | 逻辑字节 | 实际分配字节 |
|---|---:|---:|
| manifest 列出的 18 个 `model-00001-of-00018.safetensors` 至 `model-00018-of-00018.safetensors` | 55,563,006,776 | 55,563,403,264 |
| 该 27B 目录的 `.cache`，含 Hugging Face 下载锁、metadata 与 8 个零字节 incomplete 占位 | 1,312 | 61,440 |
| `runs/v015-downloads/hf-27b-tls12-firstmb.bin` | 1,048,576 | 1,048,576 |
| `runs/v015-downloads/ai-27b-curl-firstmb.bin` | 1,048,576 | 1,048,576 |
| **合计** | **55,565,105,240** | **55,565,561,856（51.749462 GiB）** |

实际分配字节依据文件 `st_blocks × 512`；缓存使用 `du -x -B1 -s`，GiB 按 2³⁰ 字节换算。模型目录在添加删除标识前由 **55,586,967,552** 降至 **23,502,848** 字节；该差值只覆盖模型目录，不包含两个目录外探针。

删除前全卷空闲为 **390,987,468,800** 字节，删除后立即读数仅增加 **4,096** 字节。北京时间 **12:25:02.644595** 的一次延后读数为 **446,521,184,256** 字节，相对删除前增加 **55,533,715,456** 字节。这些是实际观测值；文件系统释放计账和同卷其他并行任务会影响全卷读数，不能把全卷差值全部归因于本次操作。可直接归属本次删除的分配块总量是上述 **55,565,561,856** 字节。

## 保留内容与依赖核查

原 `proworksim-manifest.json`、config、tokenizer、model index、README、license 及 18 份 range journal 均保留。下载目录内的 JSON、日志和吞吐记录也保留。原 manifest 的 `status=complete` 仅是历史下载完成记录，**不再代表模型当前完整可加载**；新增 `MODEL_WEIGHTS_REMOVED.json` 明确记录 `weights_removed_not_loadable` 与清理回执位置。

9B 模型位于独立目录 `runs/assets/models/Qwen3.5-9B-c20223623576`。两个模型目录都没有符号链接或硬链接，文件 inode 集合无重合；27B 的 18 个权重均为单链接普通文件。本次删除清单没有 Git 跟踪文件。项目的 `/home/zhuxinrui/datatmp/...` 路径与 `/data1/zhuxinrui/...` 路径指向相同实际目录，不按两份模型重复计算。全局 Hugging Face 缓存没有发现该 27B 仓库；ModelScope 缓存目录不存在，未对公共缓存做清理。

当前模型 plan 与 resident owner 明确依赖 9B；base marker 指向 `runs/domain-v025-r1/train_base/actual/checkpoint-final`。9B manifest、base marker 和 checkpoint metadata 的 inode、字节数与修改时间在删除前后保持一致。

只读预查的 34 个同用户进程没有发现 27B 命令、工作目录、解释器、内存映射或打开文件引用；部分进程字段不可访问或发生竞态。执行前再检查 31 个同用户进程的映射与文件描述符，没有命中目标目录，10 个字段不可读取或已变化。这是有限进程可见范围内的核查，不是对其他用户任务或未来命令的保证。未停止任何进程。

## 执行证据

`runs/v030-cleanup/` 保存 `pre-delete.json`、`receipt.json` 与原始 `27b-original-proworksim-manifest.json`。其中记录每个删除文件的绝对路径、逻辑/实际字节、device/inode/link count、来源 revision、历史 manifest SHA 及两份 1 MiB 探针现算 SHA。原 manifest 的 SHA-256 为 `bbfeec7922f9e2bba258518df9b63a15978570c348838f55902a506829ac2050`。

删除前保存清单，再逐项确认 inode、大小与单链接身份未变，以明确路径 unlink；专属缓存使用具有防符号链接保护的 `shutil.rmtree`。没有重新计算 55.6 GB 权重的 SHA，保留的是历史下载完整校验值，不冒称本轮再次全量验证。删除后确认全部 18 个权重、专属 `.cache` 与两个探针不存在，原 manifest 字节未变，受保护元数据未变。

此次只涉及已授权资产清理与文档，未运行 pytest 或 GPU 资格测试，也不会自动重新下载已删除的旧 27B 模型。
