# 2026-10-04 存储清理记录

本次按用户授权清理历史临时文件与缓存，以不影响当前实验及其后续队列为约束。执行时间为北京时间 2026-10-04 00:18:42—00:18:46。未停止、重启实验，未修改运行代码、依赖环境、模型、正式实验结果或 checkpoint。

## 实际清理结果

只删除以下 8 个明确目录。空间采用 `du -x -B1 -s` 实际分配字节，不跟随目录符号链接；GiB 按 2³⁰ 字节计算。

| 相对项目路径 | 清理前分配字节 | 清理后分配字节 | 内容与判据 |
|---|---:|---:|---|
| `.pytest_cache` | 180,224 | 0 | pytest 运行缓存，无版本控制文件 |
| `.ruff_cache` | 57,344 | 0 | Ruff 缓存，无版本控制文件 |
| `runs/v015-runtime/tmp` | 262,991,872 | 0 | pip 安装残留：build-tracker、unpack、metadata、ephem-wheel-cache 等；不包含已安装环境 |
| `runs/v015-runtime/pip-cache` | 24,502,272 | 0 | pip `http-v2` 下载缓存 |
| `runs/v015-runtime/hf-cache` | 12,288 | 0 | 历史 `xet` 缓存；当前进程使用项目外 Hugging Face 缓存 |
| `runs/v026-checks/tmp` | 731,131,904 | 0 | 历史 `pytest-of-zhuxinrui` 测试临时夹具 |
| `runs/v026-controls/tmp` | 38,313,984 | 0 | 历史 `pytest-of-zhuxinrui` 测试临时夹具 |
| `runs/v025-r2-controls/tmp` | 24,576 | 0 | 历史 `pytest-of-zhuxinrui` 测试临时夹具 |
| **合计** | **1,057,214,464** | **0** | **释放 0.984608 GiB** |

本次删除前项目实际占用为 **166,329,454,592 字节（154.906376 GiB）**，删除后为 **165,272,240,128 字节（153.921768 GiB）**，二者差值与上述清单合计一致。这组项目测量发生在新增本记录、提交 Git 及写入清理回执之前；后续文档、Git 对象与实验日志会造成小幅变化。不能把磁盘全卷的空闲变化全部归因于本次操作，因为同卷存在其他活动任务。

## 当前实验与后续队列依赖核查

共享进程快照覆盖当时 12 个实验进程；其参数、工作目录、允许名单中的路径环境变量、打开文件和映射文件均未引用本次删除清单。针对本项目两个活动进程，还在删除前后直接核实了相同 PID 的启动标识、工作目录、解释器、命令参数、路径环境变量、打开文件和内存映射。

| PID | 启动标识 `/proc/PID/stat` starttime | 模块 | 清理前后结果 |
|---|---|---|---|
| 1220852 | `346443761` | `scripts.finish_software_allocation_v029` | 同一进程存活，工作目录及解释器路径未变 |
| 1220919 | `346443783` | `scripts.software_allocation_v029 supervise` | 同一进程存活，工作目录及解释器路径未变 |

两者从 `runs/v029-frozen-source` 运行，命令入口是 `runs/v016-sdk/resident-venv/bin/python`，底层解释器为 `/usr/bin/python3.12`。冻结工作树提交为 `6b90e9bf71455e904e6b1d2b56e2ef59dabbb7be`，与主仓库文档提交相互独立。本次未修改冻结工作树。

核查不只依赖“当前没有打开文件”，还阅读了冻结源码中的 `scripts/software_allocation_v029.py`、`scripts/finish_software_allocation_v029.py` 及当前计划、模型计划、owner recipe 和 checkpoint marker：

- 后续 support、trial、formal 任务均使用 `sys.executable` 创建子进程，继续依赖当前 resident 环境。
- 每个未来 worker 明确将 `TMPDIR`、`TMP`、`TEMP` 设置到 `runs/software-allocation-v029/<worker>/tmp`。该运行目录及其未来临时目录不在删除范围。
- 当前 `PYTHONPATH` 指向冻结源码；`HF_HOME` 和 `TRANSFORMERS_CACHE` 为 `/data1/zhuxinrui/.cache/huggingface`，`TORCH_HOME` 为 `/data1/zhuxinrui/.cache/torch`。这些项目外缓存未修改。
- 当前计划仍依赖 `runs/v029-controls/frozen-qualification.json`、`runs/domain-v0201-p1-9b/plan.json`、`runs/domain-v025-r1/train_base/actual/resident/owner.json` 及 `runs/domain-v025-r1/checkpoints/base.json`。checkpoint marker 又指向 `runs/domain-v025-r1/train_base/actual/checkpoint-final`，模型计划指向 `runs/assets/models/Qwen3.5-9B-c20223623576`。上述文件、目录及全部正式实验产物均保留。
- 收尾进程将继续使用同一解释器生成 v029 报告，并按自身既有逻辑发布该实验报告。本次未更改该逻辑或其报告文件。

删除前后 supervisor 均为 `status=waiting`、`stage=support`，observer PID 为 1220919。操作持续不足 4 秒，两次读取的 `observed_at` 相同；这只证明该短窗口内状态未发生变化，不代表实验已完成或已经通过后续 GPU 验证。

## 明确保留的空间

| 路径或类别 | 此前测得分配空间 | 保留原因 |
|---|---:|---|
| `runs/v016-sdk/resident-venv` | 5,943,566,336 字节 | 两个当前进程和后续 worker 实际使用的环境 |
| `runs/v015-runtime/venv` | 5,632,741,376 字节 | resident 环境部分入口仍存在对该环境的间接依赖，见下文 |
| `.train-venv` | 5,595,541,504 字节 | 训练环境，未纳入本次可安全删除清单 |
| `.venv`、`runs/v016-sdk/venv` | 未重新测量 | 其他现有环境均保留 |
| `runs/assets/models` | 74,917,408,768 字节 | 正式模型及 manifest，包含当前队列依赖的 Qwen3.5-9B |
| 历史及当前正式实验目录、梯度/优化器状态、checkpoints、轨迹、报告、冻结源码 | 未重新汇总 | 不根据目录时间、版本号或暂时没有打开文件推定可删除 |

**未删除 v015 环境的具体证据：** `runs/v016-sdk/resident-venv/bin/` 下的 `pip`、`pip3`、`pip3.12`、`hf`、`huggingface-cli`、`transformers`、`tiny-agents`、`httpx`、`markdown-it`、`pygmentize`、`typer` 等入口的 shebang 仍指向 `runs/v015-runtime/venv/bin/python` 或 `python3.12`；`activate`、`activate.csh`、`activate.fish` 也设置该历史环境路径。即使当前 Python 库来自 resident 环境，直接删除 v015 环境也会破坏这些入口。因此本次保留两套环境，未尝试修复 shebang 或调整依赖。`runs/v015-runtime/transformers-5.17.0-py3-none-any.whl` 及两套环境的 requirements、安装记录也保留。

## 执行边界与必要验证

删除前确认全部候选均未被 Git 跟踪，目标及其父目录没有符号链接跳转且位于项目所在设备；使用支持防符号链接攻击的 `shutil.rmtree` 按固定清单删除，不使用通配符扩展，也不跟随测试目录内的 `current` 符号链接。删除后逐项确认目录不存在，并核对释放量与项目占用差值。

原始本地回执保存在未跟踪的 `runs/storage-cleanup-20261004/receipt.json`，包含逐项字节、时间和清理前后进程身份及 supervisor 摘要。本记录保留了审阅所需的主要证据。未读取或输出 `.env` 密钥，未修改实验参数、环境文件或状态。由于没有代码变更，没有运行 pytest、GPU 实验或模型 API 调用，也没有重建已删除缓存。
