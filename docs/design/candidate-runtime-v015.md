# v0.15 候选检查点与原生训练入口

本轮将模型能力选择和在线训练兼容性分开记录。Qwen2.5-7B 的既有结果保留，但不再因已有适配而绑定后续研究。以下是官方资产核实与集成设计，不能当作 ProWorkSim 能力排名。

## 官方资产与依赖核实

核实日期：2026-09-26。所有候选均为厂商公开后训练检查点；本项目没有为候选额外生成教师轨迹或进行 SFT。

| 检查点 | 已核实官方权重 | 架构与许可 | 原生模式与本地依赖 |
|---|---|---|---|
| Qwen3.8-27B | HF revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`，18 个原始 BF16 shard，约 55.6 GB，包括视觉等模块 | `qwen3_5`，64 层，Gated DeltaNet 与 Gated Attention 以 3:1 交替；Apache-2.0 | 官方模板支持 `enable_thinking=False`；另有 `preserve_thinking` 与 `reasoning_effort`。原配置的 `transformers_version=5.8.0.dev0` 是保存配置时版本，不是最低兼容版本 |
| Qwen3.5-9B | HF revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`，4 个原始 BF16 shard，约 19.3 GB，包括视觉等模块 | 同一混合模型族，32 层；Apache-2.0 | 官方要求最新版 Transformers，并提供 `enable_thinking=False`；不能把旧 4.57.6 环境当作支持此架构 |
| Qwen3-32B | 官方公开 32.8B 稠密后训练权重，作为预先登记的集成备选；尚未在本轮下载和执行 | 64 层 GQA，64 Q／8 KV 头；Apache-2.0 | 官方指出 `<4.51.0` 无 `qwen3` 支持；模板支持非思考模式 |
| Qwen2.5-7B-Instruct | 已有本地固定 revision `a09a35458c702b33eeacc393d103063234e8bc28` | 28 层 GQA，28 Q／4 KV 头；Apache-2.0 | 官方指出 `<4.37.0` 无 `qwen2` 支持；作为历史及当前受控筛选条件 |

官方来源：[Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)、[Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)、[Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B)、[Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)、[Transformers Qwen3.5 文档](https://huggingface.co/docs/transformers/model_doc/qwen3_5)。3.5／3.8 官方页面没有提供可据以声称的唯一最低发行版本；本轮固定并实测的是 `transformers==5.17.0`，不声称它是最低版本。

## 获取与可重复身份

原 Hugging Face Xet 与标准 HTTP 大文件获取遇到连接／TLS 失败。权重改从 [Qwen 官方 ModelScope 9B](https://modelscope.cn/models/Qwen/Qwen3.5-9B) 和 [27B](https://www.modelscope.cn/models/Qwen/Qwen3.8-27B) 获取；每个 LFS 文件先核对 ModelScope 的 SHA256／字节数与上述冻结 HF revision 的 LFS 元数据相同，下载后再对实际字节核验。小配置和模板保留对应 HF revision；没有使用第三方量化或名称相近模型代替。

后续下载入口 `scripts/download_candidate_v015.py` 对每个完整 range 保存实际 SHA256，先 fsync 数据再原子写入位图；恢复时重新校验已记录 range。预分配文件的逻辑大小不计作下载进度。旧的初次并行获取脚本没有可靠的持久化 range 位图，其最终完整文件 SHA 仍严格核验；若中断，不能按 part 文件 size 宣称已下载，新入口会重取没有可信 range 记录的部分。

文件在 `runs/assets/models/`，下载过程、失败日志与完整 manifest 在 `runs/v015-downloads/`。尚未完成的下载不能标为已入场模型。共享 `/data1/zhuxinrui/models/` 与原模型文件不修改。本机已检查的个人数据目录和 HF 缓存中只发现完整的既有 Qwen2.5-7B。

依赖位于 `runs/v015-runtime/venv`，旧 `.train-venv` 不升级。为避免重复下载大 Torch 轮子，从旧环境独立复制已安装包（非硬链接），再在新环境安装固定 Transformers 5.17.0。实际成功导入的组合为 Torch 2.6.0+cu124、Transformers 5.17.0、PEFT 0.18.1；完整版本在 `runs/v015-runtime/requirements-frozen.txt`。pip 缓存与临时文件也全部在项目 `runs/v015-runtime/`。

## 共享 actor 接入

`CandidateActor` 继承同一 `SharedActor`，只替换模型加载、原生 prompt 投影和 tool 解析。采集、真实 token trace、概率准入、critic、actor optimizer、窗口更新、检查点及评价边界继续由共享训练核心执行。

1. 使用官方 `Qwen3_5ForCausalLM` 提取 text backbone 和 LM head。官方 `qwen3_5_text` checkpoint conversion 负责移除 `language_model` 前缀。保存实际 `loading_info`，拒绝缺失、shape mismatch 或未识别的语言参数；视觉与 MTP 未使用条目另外列出。不能把随机初始化语言层当作候选能力。
2. 不把旧 Qwen2.5 的 explicit-GQA attention 补丁套到 DeltaNet。初始条件使用安装版官方 SDPA 与官方 PyTorch DeltaNet 参考实现；没有安装可选 `causal_conv1d`／`flash-linear-attention`。这是一条可审查的起始数值路线，代价须实测，不能承诺高吞吐。
3. 固定 `highest` 并关闭 cuDNN TF32（混合模型实际包含卷积）；记录两类实际精度开关。固定 LoRA `r=8, alpha=16, dropout=0`，仅 `q_proj/v_proj`。在混合模型中它们只匹配完整注意力层；DeltaNet 参数冻结。保存所有实际匹配模块名并核对数量：9B 应为 16 个模块，27B 应为 32 个。没有静默改成全部线性层。
4. 起始候选 profile 为 FP32／`highest`；9B 单卡，27B 采用明确连续层分配的多卡模型并行，无 CPU／磁盘 offload。BF16 被识别为不同 profile，不能用其能力结果替代 FP32 训练准入。仅权重粗算已使 27B FP32 超出单张 80GB 卡；实际激活与缓存预算仍需记录。

## 原生接口与采样分布

官方新模板输出 `<tool_call><function=...><parameter=...>...</parameter></function></tool_call>`，不是旧模型 JSON tool block。解析器按工具公开 schema 解码数值、布尔、数组和对象；字符串（包括 SQL 中 `<` 等字符）保留。重复参数、残缺结构或不匹配类型整段拒绝，不补业务引用、隐含参数或正确答案。未知函数和缺失必需参数由原世界工具校验处理。

候选条件固定：非思考模式、16,384 总 token 上限、每次最多 2,048 输出、温度 0.7、完整 categorical softmax（`top_p=1, top_k=0`）、无重复／presence 惩罚。此采样是本项目为真实采样概率与训练概率一致而冻结的选择，**不是照抄厂商推荐的截断采样参数**。输出预算不是旧 512 上限。实际原生模板、模式 kwargs、输入 token、输出 token、每个实际采样 log probability、库版本和设备布局均保留。完整公开历史进入模板，不引入后台步骤补全。

加载时另将实际完整 `GenerationConfig` 与安装版的中性默认配置比较。除了实际 `generate` 参数明确覆盖的项目及 BOS／EOS／pad 标识，任何非中性的 `min_p`、最短长度、禁止 token、forced token、sequence bias、beam／healing 等默认项均拒绝。保存原始配置、实际覆盖项和完整有效配置，并关闭库从 model.config 再同步 generation config 的隐式兼容路径。真实候选开始采样前即固定此检查；不会仅因模板正确就假定概率路径正确。

## 分层校准与解释

`scripts/candidate_preflight_v015.py` 预先限定为两个公共工具回合：读取真实本地公共 note，再记录其中字段。之后以真实采样 token 作概率复算、可微反向和未更新检查点保存重载；不执行 actor／critic optimizer step。这测接口与数值接线，不测 SQL、复核、协作能力，也不是在线学习收益。

随机 tiny Qwen3.5 CPU 控制只用于排除官方类、cache、完整序列、LoRA 与反向的接线错误，不能当作下载中候选权重的 GPU 准入。最初 tiny 脚本误设 `min_new_tokens=8`，额外屏蔽 EOS，概率比较失败；这个脚本设置错误及原记录保留。修正为本轮明确支持的纯温度采样后再检查；没有放宽数值阈值或覆盖原记录。

真正模型工作筛选和训练准入必须分别引用后续实际运行记录。下载失败、接口失败、数值失败与业务失败不是同一个分母。


随机 tiny 三卡控制另外验证了12层混合模型的显式层映射、三个设备上真实 LoRA 梯度、实际采样与完整序列概率、全局梯度裁剪及未更新检查点重载。该短控制 max logp 差为0，三个设备均有非零梯度；它没有 optimizer step，也没有更新后的优化器状态或新世界学习证据。初始 fixture 漏填 owner 所需 manifest，在采样前失败；保留原目录并在正确 fixture 的报告中说明。没有据此声称27B已通过容量或学习准入。
