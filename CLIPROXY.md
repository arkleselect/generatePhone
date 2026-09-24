# 使用 CLIProxyAPI 账号授权生图

本机集成复用 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 的 Codex OAuth 和 `/v1/images/edits`，不提取 Chrome Cookie，不需要 OpenAI Platform API Key。能否生成、可用模型与额度取决于已授权账号的实际响应。模型列表出现不代表生图已通过实测。

## 本机使用

1. 启动 Java 后端与 Vue 前端。
2. 「账号设置 → 登录 / 连接账号」会启动本机代理并打开 OAuth 授权页面，在浏览器完成授权。
3. 回到页面，等待显示已连接，或再次点击连接账号。
   自动回调失败时，可在账号设置中粘贴本次登录的完整 `http://localhost:1455/auth/callback?code=…&state=…` 网址并点击「提交回调」。网址只交给原登录进程，不持久化；该进程验证 OAuth state 和 PKCE。`/success` 页面网址不含授权码，不能用于回调。登录进程已结束时需要重新发起登录，旧回调不能重复使用。
4. 先创建并确认一个任务，再点击「开始自动执行」。只有已确认的批次会执行；首次请检查是否有旧的活动批次。

不需要 Chrome 远程调试。登录后无需保持授权网页打开。页面中的网页期望模型不控制代理；代理请求模型由 `automation/.env` 的 `CLIPROXY_IMAGE_MODEL` 指定，默认 `gpt-image-2.5`。未知实际模型保留为空，不把请求模型伪装为已确认模型。

## 安装与配置

当前电脑使用 CLIProxyAPI v7.3.16 的 macOS ARM64 官方发行包，放在 `.tools/cliproxy/cli-proxy-api`，下载后必须对照该版本 `checksums.txt` 校验 SHA-256。其他电脑从官方 Releases 选择对应系统架构，不复制本机账号目录。

代理配置 `data/cliproxy/config.yaml`（JSON 也是合法 YAML）需要：

- `host: 127.0.0.1`，`port: 8317`。
- `auth-dir`：项目 `data/cliproxy/auth` 的绝对路径。
- `api-keys`：随机生成的本机客户端密钥；同一值保存在 `data/cliproxy/client-key`。这是本机代理鉴权，不是 OpenAI API Key。
- `request-retry: 0`，`max-retry-credentials: 1`，`max-retry-interval: 0`，避免不明确的生成请求在代理中自动重发。
- `remote-management` 设置 `allow-remote: false`、`secret-key: ""`、`disable-control-panel: true`。
- `disable-image-generation: false`。
- 如果浏览器通过系统代理访问服务，需要给 CLIProxyAPI 单独配置 `proxy-url`，例如本机实际使用的 `http://127.0.0.1:7897`。Go 服务不会自动读取 macOS 的系统代理设置。浏览器回调成功后还要换取令牌；以项目显示账号已连接为准。

这些文件只留本机，目录权限 0700、配置和密钥权限 0600，已通过项目 `.gitignore` 排除。不要提交、分享 OAuth 文件或登录日志。

`automation/.env` 设置：

```dotenv
ACCOUNT_ENGINE=cliproxy
CLIPROXY_IMAGE_MODEL=gpt-image-2.5
```

修改后重启 Java 后端及其执行器。设置 `ACCOUNT_ENGINE=browser` 可切回网页执行器。代理模式目前接入 Java/Vue 队列，独立 Python HTTP 生图入口会提示改用页面；CLI 仍使用网页模式。

## 结果与异常

每个任务都上传原始参考图；有日期 ROI 时附带同尺寸 PNG 遮罩，透明区域为允许编辑区域。遮罩并不替代人工审核。输出验证为可读取图片后保存 PNG，再导入现有审核流程，执行渠道记录为 `CLIPROXY_CODEX`。

401/403 提示授权问题，429 暂停等待额度恢复。超时、服务错误或无法读取结果会标记为待核实，不自动再生成。已有本地成功结果只重试导入，不再次请求生图。代理和授权进程由执行器管理，关闭执行器时结束其启动的进程。

日志：`data/cliproxy/proxy.log`、`data/cliproxy/login.log`、`data/browser/worker.log`。代理绑定 8317，不能与其他同端口代理同时运行。

源码参考：`internal/runtime/executor/codex_openai_images.go`、`sdk/auth/codex.go`。参考检出提交 `c404af9`。本项目通过 HTTP 调用官方发行包，没有复制其 OAuth 实现。
