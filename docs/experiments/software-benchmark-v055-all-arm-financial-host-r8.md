# v055：六条件新财务客户端与 r8 调度接入

## 目的和范围

2026-10-22，DeepSeek 六条件在一个响应触发原有全局财务门禁后停止接收新回合。r7 于北京时间 10:23:48 排空在途生成、评分和准备工作，保留 2,142 个尚未进入的原始槽位。本修订把独立审查后的 r4 财务客户端接入全部六条件；并继续使用已通过验证的 r7 次磁盘放置和阶段性磁盘预约，以便恢复后提高并发。

这是一项客户端财务处理和调度适配修订。REF/MATCH 继续执行已冻结的 r3 原生科学控制器；PROJECT 继续执行原始受管控制器。模型、思考设置、提示、工具、输出上限、种子、回合预算、评分和 3,000 个槽位清单均不改变。不能将这次 CPU/mock 控制称为完整模型实验通过，也不能据此宣称已提高实际吞吐量。

## 控制器和调度

- 新回合统一经过 `run_deepseek_episode_v055_r4.py` 和 `run_deepseek_controller_v055_r4.py`，只在独立的未来控制器进程中绑定新 API 客户端；原始磁盘文件保持原样。
- 全六条件 Agent 调用，以及 REF/MATCH 的 condenser 调用，使用同一个 r4 账本实现。原始 HTTP 请求与传输实现不变。
- r8 继承 r7 调度 tick、原有 CPU/RAM 门禁、跨队列磁盘锁、次磁盘身份验证和 100 GiB 磁盘底线。生成工作区在已准入的次磁盘，队列、账本、准备和评分保留在主磁盘。
- 总预算仍为 2,000 元，API 并发上限仍为 64。历史不确定收费和补充保留金额必须计入后续准入；新源封存不等于批准忽略原门禁。

## 必要核验与边界

复用已经完成的 `budget-runtime-r4-routing-control/receipt.json`：六条件请求负载不变、10 次模拟 Agent/condenser 调用全部绑定新客户端、三个主组生成配置均选择新入口、原生/PROJECT 分别保留原控制器，零真实 API 调用。控制所引用的四个源文件 SHA 与最终文件一致，没有重复执行该控制。

复用 `queue-resume-draft-r2/cpu-control.json`：恢复只调整队列顶层停止状态；所有历史行和异常保持不变；存在生成、评分或准备在途记录、pending 槽位已有进入证据、账本指纹变化或遗漏补充保留额时拒绝恢复。该版本明确指纹并核算 `metadata`、`requests`、`budget_adjustments`、`response_observations`、`provider_protocol_events` 和 `budget_policy_migrations` 六张表。未知表集合不会被静默忽略。

真实静止边界凭据 `queue-resume-quiescence-r1/receipt.json` 于北京时间 10:33:14 记录 858 个已进入 claims、1,966 个注册 scopes，并确认 v055 所有相关服务和 cgroup 已停止。核对时正式队列 state SHA 仍相同。Qwen 进程被明确排除，没有信号、GPU 重载、旧回合重放或正式账本写入。

最终预算资格文件仅证明隔离 CPU 与 mock 路由控制。正式账本在事故后的接受由独立 `post-incident-budget-acceptance-r1/acceptance.json` 记录；其限制必须随实验记录保留。恢复授权和实际启动回执由执行者另行保存，本文件不以准备完成代替部署或实验成功。

## 封存与证据

可审阅的小型凭据位于 `artifacts/software-benchmark-v055/all-arm-financial-host-r8/`，包括 activation、revision、恢复 CPU 控制、真实静止边界和准备好的启动 argv。这里没有复制账本、密钥、原始模型响应或 rootfs。

- activation SHA：`4b14f5098caedebfb745ff50540c2bddba3dfd01fbfd2190f7e42b48651529af`
- r8 revision SHA：`c4837307e41735fd8ae9e1b53fe62fb362bedf871e8dd31fa76edca89c011107`
- r4 qualification SHA：`e40b7a3682a37d536d53889cf14cdae18fbac3887c8b9bc519921d87848b251f`

此准备步骤未启动任何服务或调用模型。恢复后实际并发、主/次磁盘用量、CPU/RAM 和完成速率仍需要单列监测；停止期间的数据不能并入正常运行的吞吐率样本。
