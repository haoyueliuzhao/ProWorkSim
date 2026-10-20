# 固定摘要的 SWE-smith 镜像文件下载

此入口为未来缺失文件提供独立获取方式，不改正式实验的 `src/`、`scripts/`、冻结快照、模型配置、题单或已有镜像。它只下载审核后 manifest 指定的单个 config 或 layer blob，不执行 `docker pull`、`docker load`，不查询 `latest`，也不选择或升级镜像版本。

## 使用方法

先从已审核的官方 manifest 取得镜像名称、该 blob 的完整 SHA256 以及字节数，然后执行：

```bash
.venv/bin/python -B tools/domestic_registry_blob.py \
  --image 'swebench/swesmith.x86_64.<owner>_1776_<repo>.<commit>' \
  --digest 'sha256:<manifest中的64位摘要>' \
  --expected-bytes '<manifest中的准确字节数>' \
  --output 'runs/assets/<摘要>.blob'
```

示例包含占位符，不能直接执行。`--image` 必须是 `swebench/` 下的完整仓库名，不含 tag、digest 或额外 URL；所有版本选择均应在下载前完成。固定摘要和大小缺失时入口拒绝联网。

## 路由、认证和代理边界

专用 [policy](../config/domestic-registry-download-policy.json) 仅允许以下精确 HTTPS 域名：

- `docker.1ms.run`：公开 registry 接口，以及同域 `/openapi/v1/auth/token` 匿名认证接口。
- `cloudfront-docker-cf.mrs.1ms.run`：本轮 registry 实际给出的文件交付域名。

两者都是限定候选，不表示所有镜像文件或未来服务可用性已经验证。普通资产下载器的默认模型/数据域名 policy 保持原范围；registry 入口明确使用上述独立 policy。

请求使用 `ProxyHandler({})`，不继承大小写 `HTTP_PROXY`、`HTTPS_PROXY` 或 `ALL_PROXY`。registry 的匿名 bearer 认证是公开服务接口，不是宿主网络代理。token 只保存在进程内存中；认证不跟随任何重定向，单次响应最多读取 128 KiB。失败即暂停，不自动重试、切换来源、购买服务或注册账户。

下载使用真实客户端标识 `ProWorkSim-domestic-asset/1`、`Accept: application/octet-stream` 和 `Accept-Encoding: identity`。每次下载重定向先检查精确域名、HTTPS 和端口，再决定是否连接；跨 origin 时删除 `Authorization`，不会把 registry bearer 发给 CDN，之后也不会自动加回。日志不保存 bearer、认证响应正文或临时重定向 URL 的 query。

## 完整缓存与断点

入口先验证 policy、稳定 blob 原 URL、固定内容身份和本地文件，再按需取得 token。已验证完整文件的 SHA/大小和 dev、inode、size、mtime、ctime 身份仍一致时，直接复用，不重新 hash，不请求 token，也不联网。

断点的来源身份固定为：

```text
https://docker.1ms.run/v2/<image>/blobs/sha256:<固定摘要>
```

临时签名 URL 不参与断点身份。显式重新运行时重新取得匿名 token，由稳定原 URL 获取新的签名地址；原 partial 仍必须通过长度和前缀 hash 核验。续传只接受精确对应剩余字节的 HTTP 206 和 `Content-Range`；忽略 Range、改变大小或摘要、跳往其他域名时暂停，保留断点，不自动从头下载。完成后仅在完整大小及 SHA 均匹配时发布目标文件。

通用下载日志为 `<output>.download.jsonl`，保存来源、固定摘要、字节数、断点和结果；额外 `<output>.registry.jsonl` 只记录匿名认证的时间、域名、镜像、HTTP 状态、正文大小及失败类别。完整文件缓存命中时不产生新的认证事件。

## 2026-10-20 已有证据及限制

同日一次小量直连元数据检查中，32 个镜像站 `latest` manifest 的正文 SHA 和响应头 digest 均与先前保存的官方冻结 digest 相同。该步骤单独的结论是“镜像站 latest 与先前官方记录一致”，不是本机重新获取到了当前官方最新版本。

随后独立 CI run `39427123231` / job `118642369802` 于 13:03:15–18 UTC 核对官方当前 `latest`：32 项均 unchanged、unknown 为 0。该独立证据使这 32 个版本在该时点形成官方、镜像站及本地记录的摘要对应；原宿主官方连接失败记录仍保留。版本身份不由本下载工具判定，也不能单凭摘要未变推断“泄露修复版”已经发布。

初次 blob 交付请求受到 403 拒绝；其 17 字节错误正文摘要与 `error code: 1010\n` 相同，对应 Cloudflare 的客户端签名拒绝。随后一次使用真实自识别 User-Agent 和 octet-stream Accept 的 config 请求返回 HTTP 200、5,551 字节，并与固定 config SHA 完全一致。由于请求头和时点均有变化，不能把成功唯一归因于 User-Agent。该响应 `CF-Ray` 标记为 `SIN`，因此不宣称整条交付链都位于中国大陆，也不以国内服务商名称替代链路证据。

原始回执位于 `runs/software-panel-v053/image-refresh-v6/`：

- `ms-latest-32-comparison.json`
- `ms-blob-delivery-probe.json`
- `ms-config-error-diagnostic.json`
- `ms-small-layer-and-range-control.json`
- `official-latest-via-ci.json`

独立的后续交付控制取得 164 字节极小层完整内容，其 SHA 与固定值一致；对 431,740,248 字节仓库层仅请求 `bytes=0-4095`，返回 HTTP 206 和 4,096 字节，且与本地已验证层的对应前缀一致。这些控制证明该时点上述样本的交付与 Range 行为，不能证明 32 个镜像的全部层或长期服务稳定性。

以上网络和 CI 证据独立于工具的离线控制。工具实现验证只使用替代 HTTPS handler，没有通过本入口进行真实文件下载、测速、镜像导入、GPU 操作或正式实验运行。后续如进行一次真实 CLI 集成，应以其新回执单列，不能将既有网络证据冒称为本工具运行结果。

官方参考：[毫秒镜像临时拉取方法](https://1ms.run/guide/temp)、[Docker Engine 配置说明](https://1ms.run/guide/docker)、[Cloudflare 1010 说明](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/)。

## 必要离线控制

新增控制沿用真实 urllib opener 和重定向处理链，替代的只有 HTTPS 传输：

1. 匿名认证到 registry 再到 CDN 的下载流程；禁止代理环境读取，跨 origin 不泄露 bearer，日志不保留 token 或签名 query；完整缓存再次调用不联网、不重新 hash。
2. 首次响应提前结束后保留 partial；第二次使用新 token 和新签名 URL，仍按稳定 blob 原 URL 复用断点并只读取剩余字节。
3. 非法 image、缺失摘要、无效大小在认证前被拒绝；认证端点返回外域重定向时不发起第二次请求。

通用工具已有的外域/HTTP 重定向拒绝、错误 Range 不追加或回退等控制继续适用。

本次仅执行上述 3 项新增控制和受通用下载逻辑改动影响的 5 项既有控制：共 8 项通过（0.26 秒）；四个相关 Python 文件的限定 Ruff 通过。未执行全项目测试或重复任何真实网络探测。

实现完成后，根代理另执行了一次真实 CLI 集成验证，输出 `runs/software-panel-v053/image-refresh-v6/cli-smoke-164.blob`：`download_complete`，164 字节，完整 SHA 为 `8f4959350c172b12fa9307a1eed96f754d6e6cedc439854f91f9ae83cd204249`。这是新入口本身的必要集成检查；没有为此重下其他层或导入镜像。
