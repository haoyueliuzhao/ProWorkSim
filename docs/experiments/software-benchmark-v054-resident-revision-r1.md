# v054 模型常驻与逐题会话修订 r1

日期：2026-10-21，Asia/Shanghai。本文记录正式启动后暴露的环境初始化问题，以及用户要求避免反复释放显存后实施的独立运行修订。本文中的“已验证”必须以对应实际回执为准；暂存代码或合成控制不等同于真实模型常驻已经通过。

## 修订前的实际运行

原 `formal-bindings-r3.json` 于12:18启动，对应源manifest SHA `e9ed4ea2ad5a9e87bb20e373ca34037d2c17b6248ede090796077f6e31b9f2e8`。首题 `matplotlib__matplotlib-25479` 的 MATCH、REF、PROJECT 均已进入实际模型，并在既定预算边界完成唯一候选锁定及官方评分。

| 条件 | 实际模型调用 | 输入加输出 token | 未结 token | 官方代码端点 |
| --- | ---: | ---: | ---: | --- |
| MATCH | 47 | 487,531 | 0 | resolved=false |
| REF | 20 | 452,941 | 0 | resolved=false |
| PROJECT | 31 | 489,014 | 0 | resolved=false |
| 合计 | 98 | 1,429,486 | 0 | 同一题的三个条件 |

这是一个任务上的三个回合，不能作为完整500题面板的能力估计。达到预约边界时，余额不能满足下一次完整输入加最大输出预约，因此正常结束的总token可以低于500,000。没有将预算终止改写为账单异常。完整可公开状态见 `artifacts/software-benchmark-v054/formal-first-cohort-closed-r1.json`，隐藏评分细节仍留在可信评测侧。

12:26，下一题 `django__django-11276` 的 REF 槽5在领取正式题槽之前发生环境初始化故障。其回执明确 `slot_claimed=false`、`entered=false`、`model_calls=0`、`GPU_loads=0`，队列暂停新派发；已进入的 PROJECT 继续正常闭合，随后评分排空。未清除任何已进入题槽或重复其模型生成。

## Python 3.6 初始化接缝修复

固定镜像中的解释器是 Python3.6。原公开初始化脚本使用 `subprocess.check_output(..., text=True)`，该解释器不接受 `text` 关键字。错误发生在读取 Git HEAD/tree 时；此前的解释器身份、包导入、模块路径及版本检查均已通过。

修订把该处改为同语义的 `universal_newlines=True`。显式 `--continue-initialization` 仅接受已完成属主处理、保留相同任务／image／mapping、上次初始化无模型和隐藏测试、全部进程及slice已退出的失败模板。原初始化目录和失败回执改存独立历史路径，再创建一次新的初始化；不重新导出镜像、处理属主或散列大数据。

Django11276已在实际隔离环境中完成这一必要检查，模型调用和正式claim仍为0。为了不热改在途PROJECT，首次修复验证通过独立暂存模块执行，待旧回合和评分全部排空后才应用到项目源码；暂存与应用源码逐字节相同。回执为 `native-environment/python36-initialization-repair-r1.json`。暂存入口第一次仅因临时模块路径定位错误在导入时退出，未进入初始化；该错误日志单独保留。

## 显存留存与常驻目标

原执行器每题创建并关闭模型服务。文件锁仅协调本项目进程，不能阻止其他用户在释放显存后分配内存。用户明确要求“先留存显卡，并行处理修订”后，GPU7立即启动留存，GPU6等待当前PROJECT释放原GPU锁后接续；两卡均实际留存76GiB，未停止其他用户进程。

新的运行方式把模型resident与每题actor/controller分离：正常题间保留权重和GPU驻留，仅重置会话。每题依旧使用原任务、seed、独立工作区、历史、账本和候选规则；不继承上一题补丁、测试反馈或隐藏评分。不改变窗口、采样、输出上限、500,000 token、调用次数和软硬时限，也不训练或加载适配器。

GPU6的MATCH／PROJECT共享一次加载的原CalibrationActor，每题重新建立原begin_window、budget/MatchBridge与finish guard。GPU7的REF使用同一原vLLM数值服务，通过独立会话令牌隔离请求，并在正常结束时确认请求排空、清除KV／prefix状态；权重不卸载。常驻服务独立持有GPU和端口lease，每题watchdog只管理该题的CPU会话sentinel。

故障不能以“保留显存”为理由继续混用状态。账单未知、会话闭合或缓存重置失败会标记resident不可复用并暂停派发。对没有安全原样取消路径的HF在途生成，仅对已经核对身份的专用resident unit/cgroup暂停进程，保留显存；不自动恢复、重试或换槽。进程暂停并不代表已经提交给GPU的kernel瞬时撤销，未结费用仍记未知。

## 实验版本与恢复边界

原r5源清单、三个condition及相关实现快照保存在 `runner/revisions/r5/`。本次初始化和常驻改动形成新的封源及运行绑定；旧三个回合仍保留原绑定和评分缓存身份。恢复工具只允许明确证明零模型、零GPU加载、未claim／未entered的初始化失败槽进入新的准备尝试，保留原fault和attempt，不自动重启已进入的槽。

两种运行版本分别记录成本、闭合与结果。完整1500槽继续保留为进度分母；不同运行版本的结果不能直接伪装为同一配置的完整面板点估计。是否已完成真实常驻会话交接，以及是否恢复正式队列，以下续记及新回执为准。

## 实际交接结果与恢复

两种常驻模式的实际交接均已通过。GPU6的原CalibrationActor在同一宿主PID3178406、owner PID3179591及同一模型对象上依次完成合成MATCH和PROJECT会话，输入／输出分别433／2、338／2，共775 token；原RNG／只读guard、独立窗口／账本及每题缓存状态均有回执，模型加载次数保持1。GPU7的REF在同一宿主PID3199584、API PID3199698和实际GPU模型进程上完成两独立合成会话，共14,955 token，正常release实际确认unfinished=0、cache reset成功；上一会话令牌被拒绝，未新增生成。

新增交接准备共4次真实模型调用、15,730 token，未结为0，正式claim为0。此前已通过的完整输入容量检查未重跑，旧三个正式回合未重跑。公开统一回执是 `native-environment/resident-admission-r1.json`，SHA `73e7e523fe7b4932086728bba955c08b78b285b58d141a2d133e8c70a17f498f`。

REF常驻r1在权重和编译完成后，ASGI扩展导入触发项目包整体初始化，独立REF环境没有openpyxl，因此在ready和任何准备请求之前失败。修复采用stdlib独立加载ASGI模块的shim，没有扩大依赖安装或改模型数值配置。一次私有REF环境的导入检查通过，GPU／权重／网络访问均为0；失败r1完整保留，新r2服务单独命名。其间GPU7恢复76GiB占位后再交接，GPU6始终保留已通过的常驻模型。

共同宿主管理器还修正了一个状态字段接缝：MP服务健康时明确返回`poisoned=null`及`state=idle/busy`，REF返回布尔false。管理器改为分别严格核对这两种已有协议；实际poison证据仍拒绝。仅一次真实只读MP资格核验，未重复775 token控制。r6源快照另存 `runner/revisions/r6/`，本次宿主／导入修订的r7源SHA为 `73b1b45bc11d3d09c5056ba28deb1ffe6062925d0d7ccfc8ac6559a66e657061`；MP resident自身源文件未变，沿用r6启动身份，不为宿主修复重载权重。

13:11恢复正式队列，user unit为 `proworksim-v054-formal-queue-r3.service`，运行目录仍为 `runs/software-benchmark-v054/formal-queue-r1`。新binding `formal-bindings-r4.json` SHA `53429d196b077c9169d5a8a93b276fb5c76bf05a5a343139cb20ff96361f8136` 绑定当前r7、两种实际交接回执及registry-r2；registry-r2保留原GPU6声明，只替换失败的REF启动版本。

显式迁移回执 `formal-preclaim-recovery-r1/transition.json` SHA `94bc0143840c1d374c5ea2acb8e329276a9a2fecc473a9e6307d5a5a134a17ea` 保留旧state、故障及全部attempt，只有Django REF的零执行准备失败槽恢复待调度，后续目录为preclaim-2。下一批仍是原题序中的Django11276 MATCH槽4／REF槽5，PROJECT按原GPU6顺序接续。旧三回合保持旧binding；新版本与旧版本分层报告，1500只表示计划总进度，混合配置完整点估计不填数值。
