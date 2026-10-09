# v0.40 承接态组织开发变体

两个root继承已使用的v0.39 `record-views`与`record-catalog`业务合同与全部公开/私有请求—预期对，只改变初始应用分支及环境准备诊断。它们不是新来源benchmark，也不属于训练或独立确认池。原资产不改写。

| 变体 | 原root | 初始分支的两项兼容缺口 |
|---|---|---|
| sc-record-views-handoff-v040 | sc-record-views-v039 | report按组名排序而非首出现顺序；query筛选后重编号而非保留原始position |
| sc-record-catalog-handoff-v040 | sc-record-catalog-v039 | shared更新重复key时移动到末尾；query把null/false/0等假值视为缺失 |

上表是环境作者的来源说明，不是发送给成员的修复计划。`initial/`中的分支可以执行，保留大量正确行为，不是全空桩。正确reference只供CPU资格/验收侧使用；任何初始代码、缺口与诊断都不能算当前成员的工作或自主发现。

每个root包含以下材料：

- `contract.md`：业务要求与公共函数接口保留，仅更新承接态/用途说明。
- `initial/`：三个可编辑生产模块；所有成员具有同样文件与权限。
- `public-checks.json`、`diagnostic-groups.json`：同一公开检查的两组固定划分，不是任务分工。
- `acceptance.json`：原同合同私有检查，不进入初始文件或诊断。
- `reference/`与`controls/`：完整CPU正控制及API/共享产品绕过反控制，不进入模型副本。
- `initial-provenance.json`：环境作者构造说明，包含缺口来源；不进入成员观察。

源适配器`software_organization_tasks_v040.py`首次准备时实际执行两组公开driver，生成只含测试事实的`diagnostic_a`、`diagnostic_b`。失败项保留公开request、observed和expected；通过项只保留ID及状态。不发送正确补丁、任务归属、宿主路径或详细API trace。世界另绑定每条episode的baseline对象版本，并决定初始分配。

所有成员的`run_tests`仍执行一次完整公开driver，再可选执行一次成员脚本；两组诊断只是同一真实结果的投影，未增加第三次执行。I-split不是永久隐藏：成员可合法通信，也可运行同样公开测试重新取得两组事实。

同进程顺序准备同一精确初始文件和driver时复用原测量receipt。每次使用明确记录`cache_reuse`和实际新增执行数2或0；可见诊断不携带先前episode条件、宿主路径或私有历史。不同worker进程分别准备，不能把全批准备次数写成每root仅一次。原receipt保留实际CPU时间；环境准备不扣成员32次`run_tests`额度。

源manifest绑定初态、合同、诊断分组、所有检查、程序及driver；partition明确仅`organization_development`。`sha256`是排除自身字段后`json_bytes`序列化的payload摘要。详见任务控制记录`docs/experiments/software-organization-v040-tasks.md/json`。
