# v054 原始模型服务准备与有界等卡监控

2026-10-21 本轮继续完成三组评测环境。原始 Qwen3.5-9B 检查点、原配置和已验证内容不变，不挂 LoRA、不训练、不从正式 500 题挑选资格题。本文记录的是编译工具链、启动接口与容量准备，不是基准成绩。机器回执为 `artifacts/software-benchmark-v054/native-environment/model-preparation-r1.json`；动态状态以 `runs/software-benchmark-v054/model-capacity-preparation-r1/state.json` 为准。

## 已完成的工具链修复

REF 的 198 项固定依赖已经安装，但私有 Ubuntu 24 运行环境缺少 gcc、g++、ld、ninja 和 Python 3.12 开发头文件。新工具 `prepare_ref_toolchain_v054.py` 使用清华 Ubuntu HTTPS 镜像直连，取得 72 个固定包，共 92,412,656 字节；APT 索引通过 Ubuntu archive key 校验，下载包通过索引中的 SHA256 校验。没有使用代理、修改宿主已安装软件或重新下载模型／评测镜像。包版本、大小和来源在 `ref-toolchain-packages.json` 中逐项保留。这是匹配运行环境的工具链，不称为所有软件的最新版本。

`run_ref_preparation_v054.sh` 在独立 mount namespace 内叠加工具链。原运行环境 `/usr` 优先，新增层只提供缺少的工具、头文件和链接材料；可写 upper、编译缓存和临时目录留在项目范围。另在私有 `/dev` 创建 `/dev/shm`，不修改宿主设备目录。模型运行仍使用原显式物理 GPU／UUID 映射。

实际验证已编译并导入一个 C++17 Python 3.12 扩展。最初启动因私有 `/dev/shm` 挂载点缺失，在进入 Python 前失败；修复后编译通过，但在不暴露 CUDA 元数据的 CPU 环境中，vLLM CLI 初始化无法推断 device。两份失败原件保留。随后仅重做受影响 CLI 步骤，使用 GPU3 的设备元数据解析实际安装的完整参数，结果通过；`torch.cuda` 没有初始化，权重文件没有打开、模型调用为零。该观察不证明实际模型加载、长上下文推理或 CUDA 编译通过，也不把 Python 层设备打开计数为零解释成没有读取 NVML 元数据。

## 固定容量准备范围

| 服务 | 实际数值路径 | 上下文／完整输入／输出上限 | 空闲显存准入 | 实际生成上限 |
| --- | --- | --- | --- | --- |
| REF | vLLM 0.32.0，BF16，TP1，thinking，原生五工具 | 131,072／98,304／32,768 | 66,560 MiB | 2 次 |
| MATCH／PROJECT 共用 owner | 原 CalibrationActor、原 native attention／sampler，BF16 backbone／FP32 head | 18,432／16,384／2,048 | 46,080 MiB | 2 次 |

每个服务先做短合成请求，再做实际 tokenizer 计数达到完整输入上限的合成请求；计数本身不生成。保持原输出上限，允许模型自然提前停止，因此通过后也不能宣称生成了最大长度输出。输入加输出的绝对预算上界为 299,008 token，不是预计开销，不占用 1,500 个正式槽，也不授权正式 7.5 亿 token 候选预算。

容量请求只使用公开工具 schema 和人工合成内容，不读取基准题目、参考补丁或隐藏测试。记录完整 usage 和精确预约；未闭合用量保留不确定预约，不能填零。GPU 上的 parser／工具调用行为另列实际观察，不把单纯容量通过称为工具端到端通过。CPU 三组工具与生命周期证据见 [执行器准备](software-benchmark-v054-runner-preparation.md)。

## 监控与资源释放

北京时间 09:50:54 已启动项目专用 user service `proworksim-v054-model-capacity-preparation-r1.service`。源代码、owner 合同、模型 manifest 与模型文件既有 stat 回执共 23 项在运行前冻结；封源 SHA256 为 `aad1734b0196c15d7fc2b756b2621abff5bd36c1c856969253bf728661bcc07d`。不重复读取约 19 GB 权重。宿主入口使用已有项目 `.venv/bin/python`，模型服务 lease wrapper 继承同一解释器，避免系统 Python 缺少项目导入依赖。

监控每 60 秒观察一次，最多等待 96 小时；等待阶段不占显存、不启动占位进程。准备最多一个 resident，并与项目的最多四 resident／物理 UUID 锁共用。只有容量符合时才加载；不能缩短上下文、量化或借用其他进程显存。每种服务首次被准入后若失败，保留技术未知并停止，不自动换卡重试或改参数。

model unit 绑定 monitor unit；monitor 的 stop 超时为 120 秒，模型服务自己的 stop 超时为 30 秒，并用独立 service cgroup 确认 writer／子进程退出。REF 使用本地随机私有 API key 防止误连其他端口服务，密钥不写入文档、Git 或公开调用参数。三个纯 CPU 控制覆盖封源／服务身份、部分计账失败和私有 key 注入；实际 GPU 服务退出证据须等真实准备执行后形成，不能由这些控制替代。

启动时全部八张 A800 80 GB 均未满足门槛，最大空闲 15,053 MiB，因此实际容量资格仍未完成，实际模型调用为零。另一次必要的进程归属只读观察确认，13 个现存 GPU 计算进程均属于其他用户，工作目录也不属于本项目；没有本项目遗留占位可释放，没有停止任何这些进程。预计完成时间取决于其他任务何时释放显存，当前没有可靠时间可报。监控只会推进这份有限准备，正式 REF／MATCH／PROJECT 评测授权继续为 false。
