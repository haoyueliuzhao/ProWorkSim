# v0.35 P2准备：9B P1方法与实际可见信息复核

仅读取已选9B的四条已关闭P1经历。没有重跑模型、公开检查、独立验收、训练或原生分词；原业务评分与开发用途不变。

两个完整成功属于同一可观察交付机制own_tree_delivery，但位于不同根目标/先手的精确情境。不能将2/4成功改称两类支持或合并四个ξ计频，P2次类有效产出率仍未知。

| 槽 | 根目标/先手 | 原R | 类别 | 调用 | 输入token | 本人输出token |
|---|---|---:|---|---:|---:|---:|
| 0 | mm-directory-rootgoal-v034 / member_a | 1 | own_tree_delivery | 47 | 484629 | 8763 |
| 1 | mm-name-index-rootgoal-v034 / member_a | 0 | unmapped | 47 | 486189 | 10660 |
| 2 | mm-name-index-rootgoal-v034 / member_b | 1 | own_tree_delivery | 48 | 487836 | 7575 |
| 3 | mm-directory-rootgoal-v034 / member_b | 0 | unmapped | 49 | 487503 | 8672 |

191次实际调用逐一绑定原attempt、实际selected-request、原生request/render摘要、input_ids/usage及同成员原始目标。输入1,946,157、本人输出35,670，合计1,981,827 tokens。SDK裁剪前请求不替代实际选中输入；后台完整测试记录与独立验收不补入actor信息/目标。

27次实际测试中26次返回可证出现在后续实际输入。names成功槽member_b最后一次测试没有后续呈现证明。通过项被投影删去的值/stdout/API细迹不因后台保存而被认定已见。

目录成功槽：A自有v7测试（experience序号521），公开返回首见A实际输入549；B创建任务538，A领取555、固定patch-1于589、提交自己的v7于623。B在606导入A补丁并出现冲突，之后在自己副本继续工作；该支线不在最终交付祖先链。

名称成功槽：A自有v7测试463，反馈首见输入491；A创建发布任务497，未领取即发布被拒后，领取559、固定593、提交627。B于610导入A补丁并发生冲突，该支线也不是交付链。不由工具次数或模型自称推断贡献。

另两槽unmapped：names/先手A无固定交付，内容与过程未知；directory/先手B有提交，过程及其观测通过但内容失败。失败、未映射和低频经历仍按基础规则处理，不删除P2原始分母；P1本身始终禁入P2。

Mapper仅两类：可证的自有交付链；真实伙伴固定产物导入交付祖先，其元数据/回执实际呈现，至少一个完整生产文件规范内容发生变化且原字节持续保留至当前版本测试与固定交付。仅支线导入、冲突、完全撤销、手工借鉴、不确定重写不能制造第二类。

非平凡变化绑定case/source_contract中公开合同入口function/class名单。只比较这些定义的去注释、空白、docstring规范AST，排除新增无关顶层helper；不做AST作者归属或语义等价/因果价值推断。动态alias或定义不可判留unmapped。旧P1仅使用其已公开RecordSchema/catalog、NameSchema/find_matches/export_names名单。

伙伴类不要求接收者再编辑代码或逐字读取全部源码。file_materialized、import_receipt_presented与source_text_presented分列；前两者不能冒称第三者，也不证明理解或信息独立性。

精确ξ绑定window_id、xi_id、xi_fingerprint、gamma_fingerprint、team_policy_fingerprint；来源/用途、根目标、初始状态、成员、先手、调度和信息条件不能后验合并，seed只作为同ξ重复。成员继续用原member_view的本人output IDs、行为概率、labels、loss_mask，不按最终代码署名删伙伴自身动作。

API：build_software_evidence(slot_dir, rollout=..., assessment=..., expected_window=...)在entry写入前可用；map_software_method(rollout,evidence,spec=...)返回标准online_support映射及成员投影；mapping_spec()供采集前冻结。版本software-fixed-product-method-v0.35。

完整文件字节持续性和公开定义变化只是保守可识别边界，不能否定合法重写中的协作。低频门由后续精确ξ/成员统计执行；Mapper不删轨迹、不改Validity或基础actor/critic分母。
