# 工业视觉图片执行器（基于 chatgpt-image-batcher）

## 1. 上游结构与复用范围

实际克隆的是 https://github.com/matthewmiglio/chatgpt-image-batcher ，固定提交 `832ed7ce50e3d10ed9db05c76e28a51ca7bd708d`，不是假设仓库结构。

上游已有 `image_gen.py`、`src/browser.py`、`src/chatgpt.py`、`src/prompts.py` 和三组测试：持久化 Chromium 配置、一次登录、JSON 提示词批量提交、生成检测、多图选择、下载及错误分类。原来不支持参考图上传、工业缺陷定义、结构化数据集或 HTTP 服务。源码许可证情况见 [UPSTREAM.md](UPSTREAM.md)。

本次复用原函数契约及流程，扩展上传、页面定位、登录识别、下载校验、阶段重试和任务清单。`image_gen.py auth/generate` 仍保留；工业入口是 `main.py`。整个浏览器层不使用 OpenAI API Key 或 Codex 生图工具。

## 2. 文件改动及作用

| 文件 | 修改目的 |
|---|---|
| `image_gen.py` | 保留上游通用 auth/generate 入口 |
| `src/browser.py` | 扩展上游持久化配置，增加配置路径、登录检测、同一配置互斥、旧登录态迁移 |
| `src/chatgpt.py` | 扩展上游上传参考图、局部编辑提交、双图处理、等待与下载函数；校验图片真实格式 |
| `src/prompts.py` | 保留 JSON 加载/slug；增加缺陷别名与 Prompt Builder |
| `src/page_selectors.py` | 集中输入框、发送按钮和生成图片的多种定位方式 |
| `src/config.py` | `.env` 与环境变量管理 |
| `src/dataset.py` | 请求校验、命名、PNG保存、metadata/CSV/log、阶段重试及恢复 |
| `src/bridge.py` | 复用 Java 已确认队列，串行执行后回填结果 |
| `main.py` | 工业 CLI、规划预览、恢复、服务启动 |
| `service.py` | FastAPI 本机接口与进程令牌验证 |
| `../config/defects.json` | Python、Java、Vue 共用缺陷名称、输出目录、模板和适用属性 |
| `../backend/.../BrowserRunner.java` | 将进程管理切换到本 Python 执行器，保留前端原控制接口 |

旧的 `automation/worker.mjs`、`chatgpt.mjs` 和 Node 包配置已删除，避免保留两套驱动。

## 3. 目录结构

```text
generatePhone/
├── config/defects.json
├── automation/
│   ├── image_gen.py                 # 上游通用 CLI
│   ├── main.py                      # 工业 CLI
│   ├── service.py                   # 可选本机 HTTP
│   ├── src/
│   │   ├── browser.py
│   │   ├── chatgpt.py
│   │   ├── prompts.py
│   │   ├── page_selectors.py
│   │   ├── config.py
│   │   ├── dataset.py
│   │   └── bridge.py
│   ├── tests/
│   ├── examples/prompts.json
│   ├── .env.example
│   ├── requirements.txt / requirements.lock
│   ├── pyproject.toml
│   └── UPSTREAM.md
├── backend/                         # 原 Java 队列、图片、审核、导出
├── frontend/                        # 原 Vue 系统
├── data/browser/                    # 本机登录配置，不分发
└── dataset/                         # 原始候选数据集，不分发
```

## 4. 完整代码

表中每个文件均包含实际实现，可直接在本项目中打开，没有需要自行补齐的伪代码。无需另建项目或复制第二套浏览器逻辑。`tests/test_cli.py` 和 `test_prompts.py` 沿用上游；真实账号测试额外要求显式开启，默认离线检查不会打开 ChatGPT。

缺陷类型：

| CLI/API defect_type | 中文含义 | Java 历史兼容标识 |
|---|---|---|
| `date_missing` | 整段日期缺失 | `no_print` |
| `date_incomplete` | 日期不全，部分整字缺失 | `missing_chars` |
| `code_dropout` | 多字符局部掉点 | `multi_break` |
| `broken_print` | 局部断码 | `partial_break` |
| `blur` | 喷码局部模糊 | `blur` |
| `faint` | 墨迹浅淡 | `faint_print` |
| `stain` | 污染/脏污 | `stain` |
| `misalignment` | 字符基线错位 | `misalignment` |
| `ghosting` | 重影 | `double_print` |
| `normal` | 正常样本 | `normal` |

同时保留局部浅码、拖墨、异物遮挡、褶皱干扰、自定义缺陷。Java 页面支持完整位置组合和随机日期；CLI 当前是一个原图、一个类型和数量，底层任务格式预留多个类型。日期不填时沿用参考图日期；传入日期支持 `yyyyMMdd`、`yyyy.MM.dd`、`yyyy-MM-dd`。

## 5. 安装与运行

在项目根目录执行（Python 3.10+，本机验证使用 Python 3.12）：

```bash
python3 -m venv automation/.venv
automation/.venv/bin/python -m pip install -r automation/requirements.lock
```

默认使用已经安装的 Google Chrome。没有 Chrome 时：

```bash
automation/.venv/bin/python -m playwright install chromium
# automation/.env 中设置 BROWSER_CHANNEL=（留空）
```

可复制 `automation/.env.example` 为 `automation/.env`。默认值：

- `BROWSER_STATE_DIR`：项目 `data/browser/`。
- `BROWSER_PROFILE_DIR`：`data/browser/profile/`。
- `HEADLESS=false`，交互登录始终有头；后续 CLI 可 `--headless`。
- `DATASET_ROOT`：项目 `dataset/`，HTTP 的受控输出根目录。
- `INPUT_ROOT`：项目 `data/`，HTTP 的受控输入根目录。
- `MAX_RETRY=2`：单张任务各阶段共用的自动重试总预算。
- `GENERATION_TIMEOUT=900`：每轮等待生成的秒数，10–3600。
- `LOG_LEVEL=INFO`。
- `BROWSER_CHANNEL=chrome`；空值选 Playwright Chromium。

首次登录：

```bash
automation/.venv/bin/python automation/main.py auth
```

在独立浏览器窗口完成登录，再关闭窗口。登录状态在本机持久化，可能过期；不会导出到源码或元数据。上一版本保存的 `data/browser/state.json` 会尝试一次性迁移到新配置。不要同时启动 CLI 和 Java 执行器占用同一配置。

接入现有 Java + Vue：按根 README 启动系统，在“账号设置 → 登录 / 打开浏览器 → 开始自动执行”操作。Java 自动启动 `automation/.venv/bin/python main.py serve`，不用手动启动第二个 8091 服务。系统默认不会自启或自动开启生图。

Windows 使用 `automation\.venv\Scripts\python.exe`，并将 Java 的 `BROWSER_PYTHON` 设置为该绝对路径。该分支仅做了跨平台代码处理，未在 Windows 实测。

## 6. CLI 示例

从项目根目录：

```bash
# 仅规划，生成提示词和清单，不打开浏览器、不消耗账号额度
automation/.venv/bin/python automation/main.py \
  --source_image ./data/images/ham001.png \
  --defect_type date_missing --count 20 \
  --output_dir ./dataset --date_text 2026.09.24 \
  --batch_name batch_preview --plan-only

# 真实执行；等价于 python main.py --source_image ...
automation/.venv/bin/python automation/main.py \
  --source_image ./data/images/ham001.png \
  --defect_type date_missing --count 20 \
  --output_dir ./dataset --date_text 2026.09.24 \
  --batch_name batch_20260924 --max_retry 2 --headless

# 添加补充描述
automation/.venv/bin/python automation/main.py defects \
  --source_image ./data/images/ham001.png --defect_type broken_print \
  --count 10 --custom_prompt_suffix '保持轻微、自然的局部断笔，不要整字消失'

# 继续原批次（成功任务跳过，下载失败继续下载，UNKNOWN 不重发）
automation/.venv/bin/python automation/main.py resume ./dataset/batch_20260924

# 上游原命令仍可使用
automation/.venv/bin/python automation/image_gen.py auth
automation/.venv/bin/python automation/image_gen.py generate \
  --prompts automation/examples/prompts.json --output ./dataset/generic --headful
```

把示例原图路径替换成自己的图片。指定的批次目录已存在时拒绝覆盖，应使用 `resume` 或新批次名。`--headless` 不代表跳过登录验证、限额或验证码。

结果示例：

```text
dataset/batch_20260924/
├── date_missing/
│   ├── ham001_date_missing_001.png
│   └── ham001_date_missing_002.png
├── .originals/       # 原下载字节，保留 PNG/JPEG/WebP 实际格式
├── metadata.json
├── tasks.csv
└── run.log
```

主目录图片为实际 PNG，原始下载另行保留。metadata 包含来源、日期、提示词、生成时间、输出路径、状态、尝试次数、重试次数、原始下载路径、人工审核状态及未知的实际模型。生成成功不等于标签正确，候选数据默认 `review=PENDING`。

## 7. HTTP API 示例

只有脱离 Java 单独运行时，才启动本服务：

```bash
automation/.venv/bin/python automation/main.py serve --port 8091
```

服务仅监听 `127.0.0.1`。独立启动会将令牌保存到 `data/browser/api-token`（0600），不在日志中打印令牌内容。以下命令在项目根目录执行：

```bash
worker_token="$(cat data/browser/api-token)"

curl -X POST http://127.0.0.1:8091/login \
  -H "X-Worker-Token: $worker_token"

curl -X POST http://127.0.0.1:8091/generate-defects \
  -H "X-Worker-Token: $worker_token" -H 'Content-Type: application/json' \
  -d '{"source_image_path":"images/ham001.png","defect_type":"date_missing","count":20,"output_dir":"./dataset","date_text":"2026.09.24","batch_name":"batch_20260924"}'

curl http://127.0.0.1:8091/jobs/batch_20260924 \
  -H "X-Worker-Token: $worker_token"
curl http://127.0.0.1:8091/jobs/batch_20260924/tasks \
  -H "X-Worker-Token: $worker_token"
```

`POST /generate-defects` 是明确的执行指令，返回 **202**，先持久化再串行运行，避免 HTTP 请求等待几小时。响应结构：

```json
{"task_id":"batch_20260924","status":"QUEUED","success_count":0,"failed_count":0,"pending_count":20,"output_dir":"/project/dataset/batch_20260924","files":[],"metadata_path":"/project/dataset/batch_20260924/metadata.json","tasks_csv_path":"/project/dataset/batch_20260924/tasks.csv"}
```

轮询 `GET /jobs/{id}` 获取最终成功/失败数量与结果路径，`GET /jobs/{id}/tasks` 查看全部提示词和状态。重启后不自动启动旧任务：查询会标记需要检查，可 `POST /jobs/{id}/resume` 恢复；未知提交仍不会自动重发。

HTTP 相对来源路径以 `INPUT_ROOT` 为准，输出只能选择 `DATASET_ROOT`，批次名不能包含路径分隔符；CLI 则允许显式指定其他本机目录。所有接口都要求 `X-Worker-Token`，没有通配 CORS。不要把服务暴露到公网。

Java 调用的兼容接口为 `GET /status`、`POST /login`、`POST /start`、`POST /pause`；Java 管理自己的进程令牌，不使用独立服务令牌文件。控制端口默认8091，同一时间只运行一个执行器。

## 8. 稳定性、验证与扩展

- 上传前使用原始来源，逐张新开会话，避免累积缺陷。
- 上传失败和明确生成失败按预算重试；下载失败只重新下载同一结果。
- 生成超时只继续等待同一会话，预算耗尽标记 UNKNOWN；发送按钮动作结果不明也标记 UNKNOWN，不自动重复提交。
- 账号限额、登录失效和未知结果停止后续处理；不绕过验证或限额。
- 运行清单原子写入，成功任务可恢复跳过；图片 MIME/像素/真实内容检查，HTML错误页不会当PNG保存。
- Cookie 由浏览器按域名管理，下载不会把所有 Cookie 打包发送给任意地址。新增官方图片CDN域名需要检查后加入白名单。
- 模型以实际 ChatGPT 网页为准，配置期望名称不会切换网页模型。此改造没有验证2000张连续生成，也没有验证当前账号模型或额度。

离线验证：

```bash
automation/.venv/bin/python -m pytest automation/tests -m 'not e2e' -q
mvn -f backend/pom.xml test
npm --prefix frontend run build
```

真实网页测试默认禁用，需要另外明确开启 `RUN_CHATGPT_E2E=1` 并选择 `-m e2e`，会使用账号额度。它测试的是上游通用生图；参考图工业改图仍应先使用 CLI `--count 1` 做真实联调。本次未运行这些真实生成测试。

后续可扩展：通过共享配置增加缺陷；增加OCR/人工标注工具；按原图根ID分组划分训练/验证集；扩展多类型请求。单账号建议保持串行，增加并发前先确认账号能力并实现独立配置和队列隔离。当前已有 Java/Vue 任务页面，优先扩展该页面。
