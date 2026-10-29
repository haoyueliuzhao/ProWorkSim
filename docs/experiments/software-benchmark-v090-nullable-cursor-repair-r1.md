**PROJECT 分页参数适配修复（v090；CPU 验证通过，尚未部署）**

slot345 的失败来自接口适配：模型调用 `list_files({"cursor": null})` 符合模型看到的工具 schema，但固定 OpenHands SDK 在解析参数时删除了所有值为 null 的键。受管网关比较 SDK Action 与模型原始参数，发现 `{}` 不等于 `{"cursor": null}`，遂按原完整性规则拒绝执行。问题不在模型使用非法参数，也不是文件列表功能本身不可用。[原请求、实际响应及冻结源码证据](../../artifacts/software-benchmark-v090/nullable-cursor-r1/root-cause.json)。

新增 [software_benchmark_nullable_cursor_v090.py](../../src/proworksim/software_benchmark_nullable_cursor_v090.py) 只处理已确证的四个 PROJECT 分页工具：`list_files`、`read_file`、`search_file`、`diff_workspace`。修复条件必须同时满足：原 schema 明确允许可选的 string/null cursor；原参数完整通过该 schema；SDK 唯一变化是删掉显式的 `cursor: null`。随后用原参数重建 Action，再交给**原网关的完整相等检查**，实际执行仍使用原始参数，且只执行一次。

它不把空字符串、非空游标、缺失参数或任意 nullable 字段合并为同一值。新增/修改其他键、非法类型、缺失 required、未知参数均保持拒绝；required cursor、非 nullable cursor 或额外 schema 限制不在本修复授权范围。模型原始响应、SDK 原事件均保留，新增 `sdk_explicit_null_cursor_restored` 审计事件明确记录恢复了哪个字段；不伪造原 SDK 已保留 null。

未来新 PROJECT controller 可使用 `create_project_worker(*args, **kwargs)`，参数与原 `HarnessWorker` 相同；也可在新 worker **首次决定之前**调用 `install_project_nullable_cursors(worker)`。安装器拒绝重复安装、已执行 worker 和非受管 worker，要求四个工具均存在。由于 SDK 1.49.6 使用延迟初始化，并且 `tools_map` 只返回副本，安装器先完成原本就会发生的本地初始化，再在该实例原锁下复制替换四个 executor；不改 SDK 文件、类或全局映射。其余工具及公开 schema 不变。这是与固定 SDK 实现绑定的局部接口，SDK 升级后须重新核验。

本轮只完成实现和必要 CPU 验证，**没有接入 v089 或其他生产 controller，没有修改冻结 harness/SDK，没有恢复 Qwen，也没有启动新增评测**。此补丁专供 PROJECT，不能装到 REF 原生工具路径，也不能与 REF 长思考截断策略混为一项配置。

验证使用已经安装的真实 OpenHands SDK 1.49.6，输入来自明确的脚本 fixture，网关执行器只记录参数，不操作仓库或外部工具：

- 19 项参数与 schema 边界控制，确认仅修复明确允许的 null 丢键。
- 1 项原缺陷复现：原 SDK→原网关确实拒绝合法 null，执行次数为 0。
- 四工具各 4 种有效输入，共 16 项真实 SDK→新执行器→原网关验证：null、省略、空字符串、非空续页游标均原样送达一次；只有 null 产生修复事件。
- 4 项非法输入经真实 SDK 链验证，网关执行均为 0：未知参数、缺失必填项、必填 path 为 null、cursor 为数字。

以上合计 40 项控制，作为 1 个 pytest 批量测试运行通过；限定 Ruff 通过。网络、权重和 GPU 审计钩均未触发；真实模型/API/容器操作均为 0。最初测试发现宿主环境缺少可选 SDK 依赖，以及 SDK 延迟初始化/工具映射只读副本的接入细节；测试转用既有私有环境并修正新安装器，未安装依赖或更改宿主配置。完整[验证凭据](../../artifacts/software-benchmark-v090/nullable-cursor-r1/validation.json)与[CPU 结果](../../artifacts/software-benchmark-v090/nullable-cursor-r1/cpu-control.json)保留。

后续只有明确恢复实验、将新 controller 与源码重新封存后才能部署；当前实现通过 CPU 控制不代表 slot345 已恢复、已重评分，或正式正确率已经提高。
