# v0.5.4：REF 服务环境准备与离线安装

日期：2026-10-20（Asia/Shanghai）。本项只准备独立推理服务环境，不启动模型或正式任务。REF 的 OpenHands SDK 接口继续使用另一环境；不能将服务端依赖安装进已有 resident SDK 环境来改变 MATCH／PROJECT 的数值实现。

## 固定服务候选

本次固定 `vllm==0.32.0`，官方分发时间为 2026-10-18，目标 wheel 为：

```text
vllm-0.32.0-cp38-abi3-manylinux_2_28_x86_64.whl
326,518,482 bytes
sha256:5e2ecdc5b0baf72921c288486417ca82778456a448e4fe60b62ee43c0dfc8611
```

官方包元数据保存于 `runs/software-benchmark-v054/native-environment/vllm-upstream-metadata.json`。固定版本的直接依赖包括 `torch==2.13.0` 及 CUDA 13 系组件；这不是服务器 GPU 驱动已适配的证据。[官方 PyPI 版本](https://pypi.org/project/vllm/0.32.0/)。

`config/v054-ref-service.json` 保存可审阅的 REF-P1 服务和请求配置，`formal_execution_authorized=false`、`automatic_start=false`。其中总窗口为 131,072、单次输出上限 32,768、完整输入上限 **98,304**，不能把 131,072 同时当作可用输入长度。仅原始 BF16 文本模型，不挂 adapter、量化或 speculative/MTP；工具 parser 为 `qwen3_coder`，reasoning parser 为 `qwen3`，与固定原模型卡的工具用法一致。[固定 Qwen 模型卡](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)。

对已经进入本地缓存的 vLLM wheel 做了必要源码定位，确认含 `qwen3_5.py` 模型实现、`qwen3_coder` 工具 parser 注册、`qwen3` reasoning parser 注册。未从模型目录读取权重，也未导入具体模型类或启动服务。wheel 的实际完整 SHA 由后续锁定安装验收，不把 ZIP 可读取视为已通过 SHA 验证。

## 下载与缓存复用

依赖解析和下载使用现有独立 Python 3.12 `ref-venv`，清华 PyPI 镜像直连、二进制 wheels、禁代理和无外源 fallback；根进程以 `pip install --dry-run --report` 取得完整解析记录。这里的 dry-run 仍会下载依赖 wheel；“没有安装”不等于“没有网络消耗”。

已有下载进程继续运行，缓存保存在 CPU runtime 的 `~/.cache/pip/http-v2`，宿主对应路径为：

```text
/data0/zhuxinrui/proworksim-runtime/sysroot/home/zhuxinrui/.cache/pip/http-v2
```

新增 `tools/finalize_ref_environment_v054.py` 只在完整 report 已产生后收尾：

1. 校验 report 的 Python 版本、每项固定 package/version/SHA256，以及清华 HTTPS 来源；vLLM 自身额外匹配上述官方固定 SHA。
2. 按 `sha224(download_url)` 定位 pip HTTP 缓存 body，硬链接到项目 `runs/software-benchmark-v054/ref-wheelhouse/`；不扫描下载新版本、不重新请求已缓存数据。
3. 生成完整 `ref-requirements.lock` 和 wheelhouse 清单，拒绝覆盖不同的冻结记录。
4. 在独立 CPU runtime 内使用已有 pip 针对 **ref-venv** 执行 `--no-index --find-links ... --no-deps --require-hashes --no-compile` 安装；全部 wheel 内容由 pip 验 SHA。
5. 保存实际安装日志、退出码和缓存文件身份前后对照；收尾阶段网络 payload 为 0。

宿主先完成硬链接，CPU namespace 再执行 `--install-only`，避免不同 bind mount 间硬链接的 `EXDEV`。不复制第二套大文件，不修改缓存 body 或已有 SDK 环境。wheelhouse 位于已经忽略的 `runs/`；小型依赖锁、来源和安装回执位于 `artifacts/software-benchmark-v054/native-environment/`。

## 必要 CPU 检查

`tools/check_ref_environment_v054.py` 仅在安装成功后运行一次：

- `pip check` 检查完整依赖关系。
- 顶层导入 `torch` 与 `vllm`，记录真实版本、CUDA build 标识；不调用 CUDA 可用性探测或模型推理。
- 确认 CUDA 尚未初始化，CPU runtime 中没有 NVIDIA 字符设备。
- 记录 Qwen3.5 和工具／reasoning parser 的实际已安装源码 SHA。
- 审计钩子禁止网络、权重文件及 GPU 设备访问，记录实际计数。

控制环境开启 Hugging Face 和 Transformers 离线模式、禁用 vLLM 使用统计；没有加载 Qwen 模型，没有用 CPU 控制替代 GPU 容量、驱动兼容和推理数值验证。

## 持续准备与当前状态

已于 **2026-10-20 22:35:44（UTC+8）**启动仅本项目的一次性用户服务 `proworksim-v054-ref-dependency-prepare.service`，源码为 `tools/followup_ref_environment_v054.py`。它绑定原解析器 PID 与内核 start ticks，使用排他 flock 和一次性 started marker；每 30 秒观察原进程，最长等待 96 小时。服务不重启原下载、不发出新下载请求、不重试失败安装、不启动模型服务。

只有原进程退出且完整 report 已存在，才进入收尾。优先记录根进程提供的真实退出码；若尚无退出码回执，还要求最终日志含 `Would install` 成功记录，并将来源明确记为“完整报告和 dry-run 结束日志”，不虚构退出码 0。进程退出无完整报告、已知非零退出、超时或任一收尾阶段失败，都会保存失败终态并保留缓存。

持续状态及证据：

| 文件 | 用途 |
| --- | --- |
| `artifacts/software-benchmark-v054/native-environment/ref-followup-launch.json` | 用户服务实际启动命令、成功退出码和原进程身份 |
| 同目录 `ref-followup-started.json` | 排他启动标记与实际准备源码 SHA |
| 同目录 `ref-followup-status.json` | 当前等待／安装／检查阶段 |
| 同目录 `ref-followup-terminal.json` | 成功或失败终态；尚未结束时不存在 |
| `runs/software-benchmark-v054/native-environment/ref-resolve.log` | 原下载／解析进度 |

后继已于 **2026-10-20 22:56:54（UTC+8）**完成，终态为 `dependencies_installed_cpu_import_passed_gpu_admission_pending`：

| 项目 | 实际结果 |
| --- | --- |
| 最终锁定 wheel | 198 个，合计 3,940,129,591 bytes |
| 缓存复用 | 全部硬链接，没有复制第二套 payload |
| 离线安装 | 22:55:44–22:56:42，退出码 0，全部要求 SHA 由 pip 验证 |
| 安装期间缓存身份 | 未改变 |
| 收尾新增下载 payload | 0 |
| `pip check` | 退出码 0，`No broken requirements found.` |
| 顶层导入 | `vllm 0.32.0`、`torch 2.13.0+cu130` |
| torch CUDA build / 初始化 | `13.0` / 未初始化 |
| Qwen3.5／parser 源码 | 实际安装文件存在，SHA 已记录 |
| 模型加载、生成、网络、权重打开、GPU 打开 | 全部 0 |

3,940,129,591 bytes 是最终保留的依赖 wheel 总量，不是整个 resolver 的总下载流量；解析器可能曾获取后被约束排除的候选版本，不能把两个量混用。

| 凭据 | SHA256 |
| --- | --- |
| `ref-requirements.lock` | `64b6c50299de45d455253070c0453a22627d294021297b874eaebeb063c29177` |
| `ref-install-receipt.json` | `89208a9fd1073b2b60d31c491b820a2a44e8378bcc3cf0ba89b556e094c3e590` |
| `ref-cpu-import.json` | `7b59ebc8b8cba17a293bdd0590b75513bf1643f6d19e4bbb4d32073a6b15f4e1` |
| `ref-wheelhouse.json` | `4dacc0be2fd8590f75159220b7e04905382a1dee874688b69e99ca3f5c3db9ee` |

后继在根进程写入真实 resolver 退出码之前已经凭“原进程退出、完整 report、最终 dry-run 成功日志”开始，因此其历史回执保留 `resolver_exit_code=null`。根进程随后确认原工具 session 的实际退出码为 0，发布为同目录 `ref-resolver-exit.json`（SHA256 `13be8fa75e6637c54b0bbebb6563ef8d35fd3773372baa5db0e23483b9108c3c`）；不回填或改写原始后继凭据。新增 `ref-dependency-admission.json` 汇总已完成的依赖／CPU 准入和全部凭据，GPU 与正式执行授权仍为 false，固定科学配置未改变。

即使安装和 CPU 控制完成，真实 reasoning/tool-call 传输、全部模型 attempt 和 condenser token 计量、Docker task workspace／评分绑定、GPU 准入以及独立模型运行授权仍是后续正式运行条件。配置文件本身不会启动任何服务。
