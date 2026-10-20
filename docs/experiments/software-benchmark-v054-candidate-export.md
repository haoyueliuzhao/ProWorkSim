# v054 受管候选导出：完整树与两个固定终态

本修订只处理 PROJECT 的文件与候选接口，未授权或启动 REF、MATCH、PROJECT 模型评测。本文对应 `src/proworksim/software_benchmark_candidates_v054.py`；来源 provider、World 工具和受管运行入口由各自 v054 模块承接。旧源码快照、v052/v053 历史成绩及既有提交记录不改写。

## 原导出链的限制

旧 `software_bridge_sources_v052.lock_final_candidate` 调用 v051 的 `canonical_grading_tree`。该函数只支持三个 CAL-2 模块，现有修改受 `editable_paths` 约束，新文件须符合特定 Python 名称及目录规则，配置与测试会恢复为旧初态。它服务于旧小面板合同，不能作为完整 Verified 仓库的新无损导出器。仅放宽 World 的文件数量而继续使用此链，会出现新文件、配置修改或新增目录在评分输入中消失的问题。

新候选模块不调用上述 canonical，不按旧 editable 列表过滤。readonly 是 provider 的显式规则：违反时拒绝闭合，不通过恢复原文、丢弃新文件等方式把一个候选悄悄改成另一个。

## 完整文件表示

World 与 provider 统一使用完整 `files` 和 `entry_metadata`：

```json
{
  "files": {"src/tool.py": "...", "asset.bin": "<base64>", "tool-link": "src/tool.py"},
  "entry_metadata": {
    "src/tool.py": {"kind": "file", "encoding": "utf-8", "mode": "100755"},
    "asset.bin": {"kind": "file", "encoding": "base64", "mode": "100644"},
    "tool-link": {"kind": "symlink", "encoding": "symlink-target", "mode": "120000"}
  }
}
```

文本保留 UTF-8 原始字节，包括 CRLF 和没有末尾换行的内容；二进制使用规范 base64；符号链接记录目标原文，不读取其指向文件。执行权限按 Git 文件模式 100644 / 100755 保存，链接为 120000。这不保存 uid、gid、mtime、ACL、xattr 或空目录，不能称为完整操作系统文件系统备份。特殊文件、越界路径、非法编码、危险链接链及超出显式部署上限的树由共享 provider 校验直接拒绝，不截断。

正文工具是否可编辑二进制或符号链接由 World 决定。无损导出支持保留这些初始条目以及合法删除、重命名；并不由此增加二进制编辑、创建符号链接或 bash 工具。

## 同时锁定最后工作树与最后合法提交

正式闭合入口为 `lock_episode_candidates(prepared, run_root=...)`：在同一次 World store lock 内读取 baseline、当前工作树与最后合法提交。它总是锁定 `terminal_code`，并在确有合法提交时另锁 `last_legal_delivery`。没有提交时后者明确为 `None`，但终态代码候选仍完整存在；两者不是同一个评价端点。

`select_last_submission(prepared)` 从 `deliveries[-1]` 的真实 `source_reference` 读取不可变 bundle，不使用当前工作树。它核对：

- 该 source_reference 仍解析为声明的具体对象版本；
- delivery、固定 patch 与实际 bundle 的整体 hash、files hash、metadata hash 一致；
- patch 的 baseline reference 一致，变更清单覆盖 baseline/current 的并集，包含新增、删除及仅模式变化；
- delivery 引用的 public test sequence 是同 actor、同版本、已执行的真实 World 事件；
- provider 的完整树和 readonly 校验通过。

这里保留原规则：提交需要当前版本的固定 patch 和测试执行，测试不必通过。导出器不自动编辑、测试、fix_patch 或 submit。无提交时记录 `submitted=false`、`last_legal_delivery=null`，不以最后工作树替代合法交付。提交后继续编辑工作树，只改变终态代码树，不会改变已经交付的固定版本。

组合入口在同一次 World 锁内，以独占创建方式保存 `control/v054-candidate-close.json`，一次闭合同时覆盖两个端点，防止同一 World 换输出目录再次选择。它不调用另外获取 World 锁的单端点函数，因此没有嵌套文件锁。输出目录和证据文件也必须是新文件。失败不会自动换候选重试；两个唯一终态均在最终评分前锁定。此模块本身不实现或调用官方 grader。

每个端点输出包括完整 `candidate-bundle.json`、按原始字节/类型/模式计算的 `candidate-tree.json`、身份绑定、文件策略、标准 `candidate.patch`、patch 往返回执和端点 `lock.json`。组合 `lock.json` 分别引用 `terminal-code/` 和 `last-legal-delivery/` 的锁；`read_episode_candidates` 核对后返回两个完整 bundle，单端点读取由 `read_locked_candidate` 完成。

若两个端点的完整 bundle、baseline 和文件策略一致，可复用已经生成的内容和补丁文件，同时保留各自 binding；否则独立导出。代码树相同本身不授权重用评分，还须完整 evaluator 身份相同。当前只记录这一条件，没有调用或自动复用任何评分。旧 `lock_last_submission` 单端点辅助函数保留；v054 正式集成使用组合入口，不能分别调用两个闭合入口。

## 标准 Git 补丁的无损生成

在隔离临时目录中新建空 bare Git 库，只使用 object/index plumbing：

1. 将每个条目的真实 payload 作为原始 blob 写入，`hash-object --no-filters` 不经过 clean filter、换行转换或 working-tree encoding。
2. 用显式 mode、blob ID 和 NUL 分隔路径构造 baseline/候选两个完整 tree。
3. `git diff --binary --full-index --no-renames --no-ext-diff --no-textconv` 产生标准补丁。重命名表示为删除与新增，保留的是精确终态而非猜测的 rename identity。
4. 将补丁应用到 baseline index，再比较得到的 Git tree ID 与目标 tree，确认字节、存在性、模式和链接目标全部一致。

系统与全局 Git 配置被隔离，hooks、外部 diff 与用户 attributes 配置禁用，不继承 `GIT_DIR` 等环境。仓库自身 `.gitattributes` 作为普通文件保存，不能触发宿主 filter。此过程不访问项目 `.git`，不提交、推送或联网。

`materialize_tree` 只写全新目标目录，先创建普通文件、最后创建符号链接，不沿候选链接写入。它与标准补丁是同一完整树的两种导出形式。

## 必要验证记录

五项必要 CPU 控制已通过，未接触真实题或模型：

- 230 个额外文件、40 KB 文本、新增空文件及 Unicode 路径、配置修改、文件删除与重命名、CRLF、二进制、执行位和符号链接，经过 Git patch 精确应用及物化再捕获后相同；宿主伪造 Git 配置和 `GIT_DIR` 不生效。
- 仅执行位变化、删除到空树以及空树不变的补丁都能闭合。
- 真实 provider → 新 World / Port 执行 create/delete/rename、配置修改、固定 patch、实际 CPU 合成测试、submit，随后闭合。合成测试故意失败，但确实执行；同版本固定提交仍合法，证明没有偷偷增加“测试必须通过”的门。
- 同一链在提交后再编辑工作树：两个端点保持各自版本，最后交付不含新改动。删掉固定 patch 的新增路径记录或篡改测试 source hash 时，选择阶段明确拒绝，不重新运行测试来修补证据。未再编辑的配对控制则复用相同候选内容文件。
- 没有任何提交时，终态代码树仍完整导出，交付端点为 None；没有自动测试、固定 patch、submit 或评分。任何第二输出目录的再次闭合都会被一次 close claim 拒绝。

执行顺序为首批 2 项纯 Git/物化控制通过，再运行新增 3 项 World 链控制通过；补入篡改证据断言后只重跑受影响的提交后编辑场景（1 项通过），没有重跑无关控制。初次限定 Ruff 报告测试文件预留但未使用的两个 import；真实 World 控制使用这些 import 后，限定 Ruff 通过，新增断言后仅检查变动的测试文件也通过。

以上证明的是合成接口链和文件保真，不是 Verified 官方测试通过、模型能力提升或 500 题准备完成。根集成另有 HarnessPort / 新 S1 runtime 装配控制，本模块没有重复它们；仍没有新增模型评测或正式 grader。
