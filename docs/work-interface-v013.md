# v0.13 公开工作接口

`work_interface.WorkInterface` 为在线短任务声明公开动作集合与观察呈现。世界状态和权限仍由 WorldCore 管理；该层不能补答案或代做采用/提交。

## 动作

- `read_alias(alias, work_id?)` 读取公开工作空间别名；不接受 object_id/version_id 混合字段。
- `read_version(reference, work_id?)` 要求 `reference={object_id,version_id}`，按确切版本和原权限读取。
- 读结果返回规范 exact reference；工具没有自行判定“正确业务依据”的分支，错误/旧版/私有引用仍由世界拒绝或作为实际读入内容留存。
- provider/implementer/reviewer 分别公开6/13/11个世界工具；原 ModelPolicy 另加 staff_wait/staff_done 控制。类型、必填、互斥/条件字段和嵌套reference完整声明。write_object用alias，不接受隐式object_id兼容修正。

校验在真实 `world.act(...project_action...)` 命令内部执行，`interface_profile` 是绑定端口的可信参数，不能由模型自行更换。错误有正式 command receipt，不会变成日志层伪造返回；拒绝后在岗位预算内继续显示真实反馈。schema只约束公开语法，没用约束解码，也不改实际生成概率。

## 观察

新接口保留 observation 的全部非projects字段。projects仅保留title/description/status/participants；裁掉重复的场景注册和初始化包，实际权限、工作要求、版本元数据、可见对象、采用、交接和问题仍使用原观察。每次写出原始观察、公开观察、JSON摘要与字节数，独立capture只记录模型实际端口输入/输出；ModelPolicy再保存真正发送请求和prompt选择依据。不能从日志全集回填成员输入。

旧接口对照仍暴露原工具定义（不含新增的两种read），observe保留完整原值；两者的差异是整个声明接口配置，不将结果归因成某个schema字段的单因素效应。

## 验证边界

单元/CPU集成验证歧义引用和未知字段原样拒绝、正确读有真实receipt、未读证据/私有版本不自动修正、原观察投影可核、实际参数拒绝后同岗位仍可继续。真实模型的读取/交接/错误调整结果单列于[实验报告](experiments/online-v013.md)，不能由语法可用性推出业务学习收益。
