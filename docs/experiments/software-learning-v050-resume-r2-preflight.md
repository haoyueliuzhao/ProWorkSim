# v050-r2启动前回执

[接续协议](software-learning-v050-resume-r2-protocol.md)已固定。新实现位于独立工作区/分支，原主工作区仍为abc30f7，保护在GPU2运行的原Q+。

[CPU总门](software-learning-v050-resume-r2-cpu-controls.json)通过43项不同控制：compute19、host24。累计68次案例执行为67通过、1失败，最终所有不同案例均通过。唯一pytest失败是模拟监督器fixture漏stub资源查询，fake Popen在实际nvidia-smi执行前拒绝该命令；已修fixture，未改变科学协议。两次Ruff发现分别为fixture lambda赋值和未使用import，均修复；最终整个src/tests/scripts Ruff通过。compute五次sandbox初始化失败没有执行项目代码，初小回执误记六次已在最终回执纠正，原件保留。

一次真实JSON/源码消费证明原1032冻结文件同字节、24条材料及四个Q开发分片4/4/4/4准确对应；没有再次运行Mapper、训练准入计算、模型资格、真实验收或分词。独立17项旧Q−边界绑定检查和独立接线审阅通过。旧Q−191行确认完成、第192行未决、optimizer0及剩余130910.079967秒均有原件和源码次序凭据。

[证据目录](software-learning-v050-resume-r2-evidence/manifest.json)保存小型原始控制输出和SHA引用，包含失败。所有启动前控制新增真实模型/GPUworker/反向/参数更新/张量加载均为0。真实启动须在新source commit冻结后由监督器重新检查GPU4优先及原60秒稳定门，现有Q+计入总驻留上限三。
