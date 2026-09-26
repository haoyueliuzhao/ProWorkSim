# v0.15：固定公开软件来源与有界维护责任

本线将 Marshmallow 的实际 Python 源码装入现有世界。第一版是一个实现岗位的维护责任，另有独立的提交复核；它不是多成员交叉开发的完成声明，也不是在线训练结果。源代码、MIT 许可、原始测试和选定文档保留原字节。项目合同、消费者程序、岗位和工作流程是本研究新构造的模拟需求，不冒充上游历史 issue。

## 来源与范围

官方仓库：[marshmallow-code/marshmallow](https://github.com/marshmallow-code/marshmallow)。固定 tag `4.3.1`，commit `c7b559a1fa3aba57ca6dba0ab336841c5038a782`；原许可见 `examples/software-v15/upstream/LICENSE`，原 NOTICE 同时保留。官方字段说明见 [Fields](https://marshmallow.readthedocs.io/en/stable/marshmallow.fields.html)。源码的 `String` 原实现接受字符串/字节、使用原 UTF-8 错误路径，尚无本任务新增的选项。

`source-manifest.json` 保留每个选定上游文件的 SHA256；获取后又从固定 Git commit 逐个读取并核对了归档字节。归档为有界子集：所有 `src/`、所有原 `tests/`、README、许可/NOTICE、pyproject 及两份使用文档。未执行完整上游 pytest 回归，不能将本轮的 3+12 项新合同检查写成完整仓库兼容性证明。

Click 仅作为事先登记替代：只有 Marshmallow 无法取得、许可不准入或无法在声明隔离条件下运行时才能切换并记录具体原因。本轮 Marshmallow 通过，不切换。

## 公开工作合同

新增 `String(strip_whitespace=False)`，只在显式开启后的反序列化阶段去除首尾 Unicode 空白；先保留现有解码和非法类型行为，验证器接收归一化结果。默认/False 和序列化保持原行为。消费者 `InventorySchema.sku` 开启该选项，description 不开启。公开合同还明确 `allow_none`、`required`、`data_key`、嵌套及已有 String 子类兼容性和参数文档。

仅允许改 `src/marshmallow/fields.py` 和 `consumer.py`。源码在世界中是一个带文件映射的版本对象，而不是宿主目录。模型通过公开工具自行定位、读取、替换、测试、提交；控制器不替模型生成补丁或补交结果。18 次决策是第一版固定上界，未按结果追加。参考补丁只用于规则见证，不作为教师轨迹或模型输入。

可见 3 项例子只覆盖默认保留、开启后的普通空格、消费者 SKU。独立验收保持 12 组性质，拆为 29 个实际 API 输入，覆盖 UTF-8、Unicode/内部空白、非法类型、None、验证顺序、dump、参数签名和文档、别名/嵌套等。**全部 expected、分组、逐项比较和定位由可信父进程持有。**隔离子进程只收到 API 输入和通用调用适配器，执行实际源码，返回值或异常；没有 expected、断言或通过/失败判据进入执行模型代码的进程。私有 fixture 和参考补丁不装入世界、不出现在文件索引中、不能由角色工具读取。父进程检查完整观察数量、类型和值，重复/缺失/不完整响应不能成为通过证据。

这项进程边界修订来自真实反例：在 fields.py 顶层 monkeypatch `unittest.main`，即可让旧版可见与私有 unittest 驱动不运行检查而正常结束，得到错误 R=1；完成 nonce 只能识别某些提前退出，不能证明测试真的执行。原错误结果保留，旧 `private/test_acceptance.py` 只作历史复现资产，不再用于评分。新验收不导入或信任子进程的 unittest，攻击仍可令可见驱动声称成功，但父进程会从实际 API 输出判失败。源码只接受有限输入下的业务检查，不宣称由 29 个输入证明所有未来行为；操作系统隔离、子进程输出与父进程质量判断仍分别记录。

## 与既有语义内核的关系

`SoftwareWorldCore` 是独立模块中的扩展，复用 WorldCore 的权限、单写者命令日志、不可变对象、提交和复核。`read_source`、`search_source`、`replace_source`、`run_tests` 均是实际 world command，有自己的参数、journal、operation_commits 和结果，不伪装成 `write_object`。

部分源码暴露记为 `knowledge.source_ranges` / `source_searches`；不把一段文本声称为已读整个源码包。`replace_source` 要求唯一精确前像，写入新版本。`run_tests` 从当前精确版本重建独立目录，记录实际输出和源版本 SHA，将 `test_result` 的依赖绑定到执行源码。`submit`、`inspect_submission`、issue 和 approve 使用原 WorkInterface；必须由模型明确提交 `source` 和 `test_result`。模型可见端不提供任意 `write_object`、任意 shell 或任意测试命令。

最终 `assess_software_submission` 只使用真实 submission 固定的 `artifact_versions` 重建代码；工作区之后的修改不影响该提交。测试报告必须引用同一个提交源码版本和 bundle SHA，不能拿旧报告验收新代码。父进程 29 项 API 检查全部通过，且存在真实匹配、正常结束的可见执行报告，才得到本片段 R=1。可见驱动的成功声明另记为 `submitted_visible_driver_claims_pass`，不把它当作独立正确性判断。世界结构性批准不自动等于业务通过。没有提交为可评价失败；隔离设施无法安装时为 unknown，不能当业务失败。主动撤回或失效的提交不能作为当前成果，返回 R=0。此接口尚未接入既有 online_support 的软件分项许可证明或参数训练准入，明确 `training_supported=False`。

接口：

```python
from proworksim.templates.software_maintenance import (
    build_software_case, SoftwareMaintenancePort, assess_software_submission,
)
prepared = build_software_case("marshmallow-v15-strip-implement", new_root)
port = SoftwareMaintenancePort(prepared.world.session("implementer", "SOFTWARE"), "implementer")
# port.tools(), port.observe(), port.call(...) compatible with ModelPolicy/StaffRuntime
# Private assessment is called only after the actor trajectory has closed.
report = assess_software_submission(prepared, run_root=assessment_root)
```

独立有限试跑可调用 `proworksim.software_collection.collect_software_episode(config, output_dir, transport=shared_owner.transport, model_identity=shared_owner.freeze_identity())`。调用方先冻结模型/采样配置；函数不加载权重或触发参数训练，只绑定 implementer 的 18 次机会。它保存真实 ModelPolicy 请求与返回、StaffRuntime 捕获、episode 起终不可变快照，并在对话闭合后运行私有复核；没有模型提交时返回 R=0。该记录不可直接冒充通过现有训练准入的在线样本。

## 实际隔离与资源

预检发现当前用户无 Docker socket 权限，sudo 需要密码；user namespace 映射被宿主拒绝，随 Codex 的 bubblewrap 在设置 loopback 时失败。因此没有把普通 cwd 当容器使用，也未改宿主权限。采用宿主已有 **Landlock ABI 4＋libseccomp**，声明最低 ABI 3，缺失则 fail closed。

每次固定 Python 测试创建全新源码目录，输入只有经过相对路径检查的文件映射，不接受 symlink、任意宿主文件或可执行命令。`/usr/bin/python3 -I -S` 清空环境与继承路径，仅保留该目录、系统标准库及必要只读原生库。Landlock 不授予任何写权限，读权限只限该次源码树和必要 Python runtime，不含项目根、控制目录、私有资产、其他项目、`/proc` 或网络配置。实际代码导入自物化目录的 `src/marshmallow`，父进程比较 API 查询返回的 `fields.__file__` 相对路径，不会运行原 checkout 或环境中另外安装的 Marshmallow。

seccomp 拒绝 socket/network、clone/fork/exec、ptrace、跨进程内存、mount/namespace、io_uring 等入口。rlimit：CPU 10 秒、地址空间 512 MiB、64 个 fd、禁止新进程、禁止 core；父进程另施加 20 秒墙钟上限和 256 KiB 输出文件上限。固定测试在只读源码内完成，不需要写缓存。源码区甚至不能写自己的文件；编辑动作由隔离外的可信 WorldCore 按显式模型请求完成。提前 `os._exit(0)` 不产生完成标记，不视为测试完成。

这是一套 Linux 单机资源与访问控制边界，不是 VM/独立内核；文件元数据可见性等 Landlock 非目标范围不被宣称隐藏。主机内核及许可的系统运行库仍属于可信计算基础。共享 GPU 不涉及本 CPU 资产验证；真实模型试跑的资源另记。

## 来源和泛化解释

Marshmallow 成为一个与构造 SQL、UCI 数据不同的软件来源。由于本轮用于环境开发和候选模型试跑，它属于开发来源，不能再当作从未接触的独立测试家族。源码可能存在于基础模型预训练中；本轮新需求减少简单复现旧补丁的捷径，但不能保证零污染。角色不可见的独立合同测试，不等于独立来源泛化或训练收益。
