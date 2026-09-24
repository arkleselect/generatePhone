# 火腿肠生产日期缺陷图片批量生成系统

用于制作工业视觉训练候选数据：上传火腿肠参考图，配置生产日期、缺陷类型和数量，通过自己的 ChatGPT 网页账号生成图片，再进行审核和导出。

- 前端：Vue 3、TypeScript、Element Plus。
- 后端：Java 21、Spring Boot、MySQL，本地保存图片。
- 生图执行器：基于 [chatgpt-image-batcher](https://github.com/matthewmiglio/chatgpt-image-batcher) 改造的 Python + Playwright 程序。
- 不使用 OpenAI API Key，不需要 Codex 逐张执行；登录状态保存在本机。

**当前版本已通过离线测试和构建，真实网页上传、生成、下载流程仍需单张联调。请先测试 1 张，再扩大批量；尚未验证连续生成 2000 张。**

## 1. 当前电脑快速启动

以下命令适用于已配置好的这台 Mac，项目位于：

```text
/Users/mortysmith/Documents/myDev/generatePhone
```

现有 `.env` 已保存数据库配置，Python 依赖和前端依赖已安装，后端 JAR 已构建。**无需重新初始化数据库，也不要用 `.env.example` 覆盖现有 `.env`。**

打开三个终端窗口，依次启动数据库、后端、前端。运行期间保留这些终端。

### 终端一：启动项目数据库

```bash
cd /Users/mortysmith/Documents/myDev/generatePhone

# 启动本项目专用 MySQL，使用 3307 端口和独立数据目录。
mysqld --no-defaults \
  --datadir="$PWD/.tools/mysql-data" \
  --socket="$PWD/.tools/mysql.sock" \
  --port=3307 \
  --bind-address=127.0.0.1 \
  --mysqlx=OFF \
  --log-error="$PWD/.tools/mysql.log" \
  --pid-file="$PWD/.tools/mysql.pid"
```

数据库运行日志在 `.tools/mysql.log`，终端没有持续输出也可能是正常运行。

### 终端二：启动 Java 后端

```bash
cd /Users/mortysmith/Documents/myDev/generatePhone

# 加载本机数据库配置，不打印密码。
set -a
source .env
set +a

# 使用绝对路径，避免启动位置不同导致图片或执行器目录变化。
export STORAGE_DIR="$PWD/data"
export BROWSER_DIRECTORY="$PWD/automation"
export BROWSER_PYTHON="$PWD/automation/.venv/bin/python"

# 使用项目已安装的 Java 21 运行已构建的后端。
.tools/amazon-corretto-21.jdk/Contents/Home/bin/java \
  -Djava.awt.headless=true \
  -jar backend/target/hamlab-1.0.0.jar
```

看到 Spring Boot 启动成功日志后，后端地址为 `http://127.0.0.1:8080`。

### 终端三：启动 Vue 前端

```bash
cd /Users/mortysmith/Documents/myDev/generatePhone

# 启动开发页面，/api 请求会代理到 Java 后端。
npm --prefix frontend run dev
```

浏览器打开：**[http://127.0.0.1:5173](http://127.0.0.1:5173)**。

### 检查服务是否正常

可在另外的终端执行：

```bash
# 后端和数据库正常时返回 {"status":"UP"}。
curl --fail http://127.0.0.1:8080/api/health

# 查看当前服务端口。执行器未启动时，8091 没有监听是正常的。
lsof -nP -iTCP:3307 -iTCP:8080 -iTCP:5173 -iTCP:8091 -sTCP:LISTEN
```

| 服务 | 本机端口 | 启动方式 |
|---|---|---|
| 项目 MySQL | 3307 | 终端一 |
| Java 后端 | 8080 | 终端二 |
| Vue 前端 | 5173 | 终端三 |
| Python 浏览器执行器 | 8091 | 在页面点击“登录 / 打开浏览器”后由 Java 启动 |

**使用 Java + Vue 页面时，不要另外手动运行 Python HTTP 服务，否则会发生端口或浏览器配置占用冲突。**

## 2. 登录账号与首次单张测试

### 登录账号

1. 打开页面，进入「账号设置」。
2. 点击「登录 / 打开浏览器」，系统会打开独立浏览器窗口。
3. 如果未登录，在该窗口登录自己的 ChatGPT 账号；已保存且有效的登录状态会复用。
4. 登录后回到系统，点击「开始自动执行」。

开启执行器后，它会处理已确认、处于执行状态的账号批次。草稿和已暂停批次不会因此自动开始。登录、验证码或额度问题需要在浏览器处理，保存登录状态不代表永不过期。

### 原始参考图与姿势底图库的区别

| 类型 | 用途 | 后续操作 |
|---|---|---|
| 原始参考图 | 提供产品外观，用于生成正常姿势底图 | 可用于阶段 A |
| 姿势底图 | 提供正常日期、明确的编辑区域，用于生成缺陷 | 人工审核通过并框选日期区域后，可用于阶段 B |

如果已有真实、合格的正常照片，可以在上传时选择「真实合格底图」，直接进入审核和框选流程，跳过阶段 A。

### 只测试 1 张缺陷图

1. 将一张正常产品照片拖到图库，上传用途选择「真实合格底图」。
2. 在「姿势底图库」点击「审核底图」，确认 `normal / OK`。
3. 点击「框选日期区域」，框住生产日期喷码并保存。
4. 在「创建批量任务」选择「阶段 B · 生成日期缺陷」，只选这张底图。
5. 将「位置覆盖方式」改成 **「随机采样」**。
6. 缺陷配置清单只保留一种，例如「日期不全」；每组张数设为 **1**。
7. 选择指定日期或随机日期范围，执行模式选择「账号生图」。
8. 检查右侧总数为 **1**，预览提示词后再确认执行。
9. 在「任务与历史」查看当前提示词、状态和生成结果。

**默认“全部位置组合”不是单张模式。即使重复张数为 1，一个 8 位日期的字符缺失也可能展开为 255 个任务。以页面显示的总数为准。**

如果只有原始参考图，可以先在阶段 A 选择一张参考图、一个姿势、数量 1，生成正常底图，再审核、框选并进行上述测试。

此前已暂停的批次需在任务页点击「继续任务」。同一时间只有一个等待账号结果的任务；旧批次若已有等待结果的任务，需先继续处理或按异常恢复流程处理，避免阻塞后续批次。

## 3. 批量生成与缺陷配置

支持日期缺失、日期不全、掉码、断码、模糊、浅淡、污染/脏污、错位、重影、正常样本，以及局部浅码、拖墨、遮挡、褶皱干扰和自定义缺陷。

定义集中在 [config/defects.json](config/defects.json)，Python、Java 和 Vue 共用。修改该配置后，需要重新构建并重启 Java 后端，同时重启执行器。

### 日期和位置覆盖

- **全部位置组合**：覆盖数字位置的全部非空组合。8 位日期共有 `2⁸ − 1 = 255` 种；“多字符掉点”排除单字符组合，共 247 种。
- **连续位置组合**：8 位日期共有 `8 × 9 ÷ 2 = 36` 种连续数字位置组合。
- **随机采样**：每张自动采样日期、缺陷位置和适用的程度等参数。
- 完整覆盖模式先处理指定日期，再逐个覆盖追加的不重复随机合法日期。
- 日期分隔符不作为受损目标，相同数字出现在不同位置会分别处理。

例如：一张底图、仅选择“日期不全”、8 位日期、追加 7 个随机日期、每个组合 1 张，合计 `255 × 8 = 2040` 张。

每批最多 **5000** 个任务。位置组合可以穷举，但污损形状、程度和外观不是穷举。全部具体日期和提示词在草稿预览时确定，确认后冻结；重试不会重新随机生成参数。

## 4. 查看、审核、删除与导出

- 「任务与历史」显示当前提示词，并可切换查看已生成、待执行、异常任务。
- 图库支持“小图模式”，减少文字信息、增大图片展示面积；点击图片可查看原图。
- 可逐张选择或选择本页后批量删除，单次最多 200 张。
- 删除仅适用于未被引用的原图或底图。已有任务（包括草稿）或生成图片引用时会阻止删除；批量删除中有一张被引用，则整批保留。
- 生成结果默认待审核。预期缺陷、人工标签与 `OK/NG` 质量判定分别记录。
- Java 导出默认仅包含人工审核通过的结果，测试模式图片永远排除。
- ZIP 中包含生成图片、`manifest.jsonl` 和 `generation-config.json`。

Python 执行器同时保存候选数据集：

```text
dataset/java_<批次ID>/
├── date_missing/
├── date_incomplete/
├── blur/
├── normal/
├── .originals/       # 原始下载字节
├── metadata.json    # 原图路径、提示词、输出路径、状态、重试次数等
├── tasks.csv
└── run.log
```

仅实际涉及的缺陷类型会创建目录。候选数据集不代表人工审核通过；建议按 `root_source_id` 分组划分训练集和验证集，避免同源近似图片跨集合。

## 5. 暂停与关闭系统

### 暂停任务

在任务页点击「暂停后续任务」，或在「账号设置」点击「暂停执行器」。已经向网页提交的生成可能仍在继续，暂停不能撤回它；建议等当前结果下载保存后再关闭服务。

### 关闭服务

1. 暂停不希望下次继续处理的批次，再暂停执行器。
2. 在前端终端按 `Ctrl+C`。
3. 在后端终端按 `Ctrl+C`。Java 会请求关闭自己启动的 Python 执行器和浏览器。
4. 关闭本项目数据库。先检查 PID 确实对应 `.tools/mysql-data` 的进程，再发送正常终止信号：

```bash
cd /Users/mortysmith/Documents/myDev/generatePhone

# 核对进程命令中的数据目录，确认是本项目 MySQL。
ps -p "$(cat .tools/mysql.pid)" -o pid=,command=

# 确认后正常停止，不删除数据库和图片。
kill -TERM "$(cat .tools/mysql.pid)"
```

若 PID 文件不存在，先通过前述 `lsof` 命令检查，不要停止其他项目的数据库。停止服务不会删除图片、任务记录或本机登录状态。

## 6. 常见问题

| 问题 | 处理方式 |
|---|---|
| 页面打不开 | 检查前端终端是否启动成功，以及 Vite 实际显示的地址和端口 |
| 页面提示请求失败 | 检查后端日志及 `/api/health`，确认数据库已启动 |
| 数据库连接失败 | 当前电脑使用 3307；检查根目录 `.env` 中的 `DB_URL`，不要覆盖已有密码 |
| 端口已占用 | 用 `lsof` 查看占用者，避免重复启动同一个服务 |
| 提示 Python 环境未安装 | 检查 `automation/.venv/bin/python`，按执行器文档安装依赖 |
| 独立浏览器打不开 | 检查 Google Chrome、`BROWSER_PYTHON` 及 `data/browser/worker.log` |
| 提示浏览器配置正在使用 | 关闭另一 CLI/执行器，同一浏览器配置不能同时被多个进程占用 |
| 任务一直等待 | 检查登录、执行器是否启用、批次是否暂停，以及是否有旧任务占用队列 |
| 上传或页面定位失败 | 查看浏览器和 `run.log`；真实网页可能改版，离线测试不保证选择器始终有效 |
| 图片下载失败 | 已生成结果可重试下载，不需要重新发送提示词 |
| `UNKNOWN` / 结果待核实 | 先检查原网页会话；有结果时通过任务里的手动导入工具回填，不要直接重复生图 |
| 账号限额或登录失效 | 在网页处理后再恢复，不会自动绕过限额或验证 |
| 实际模型与期望名称不同 | 设置里的名称只是偏好，不会替你切换网页模型；以 ChatGPT 界面为准 |

自动重试默认总预算为单张 2 次。上传失败和明确生成失败可重试；下载失败只下载原结果；等待超时只继续等待同一会话。预算耗尽且结果无法确认时保留为待核实状态。

更多恢复说明见 [ACCOUNT_WORKFLOW.md](ACCOUNT_WORKFLOW.md)。

## 7. 修改代码后的验证与构建

以下命令均在项目根目录执行，不会实际调用 ChatGPT 生图：

```bash
cd /Users/mortysmith/Documents/myDev/generatePhone

# 使用项目 Java 21 运行测试并重新打包后端。
export JAVA_HOME="$PWD/.tools/amazon-corretto-21.jdk/Contents/Home"
mvn -f backend/pom.xml package

# 前端类型检查和构建。
npm --prefix frontend run build

# Python 离线测试，排除真实账号测试。
automation/.venv/bin/python -m pytest automation/tests -m 'not e2e' -q
```

Java 或共享缺陷配置修改后，用新 JAR 重启后端。Python 修改后需重启执行器。前端开发模式会热更新大多数修改。

现有验证记录见 [VALIDATION.md](VALIDATION.md)。真实账号测试需要另行显式启用，会使用账号额度。

## 8. 新电脑安装

需要 Java 21、Maven 3.9+、Node 22.12+、Python 3.10+、MySQL 8.4+ 和 Google Chrome。源码包不包含 `.tools/`、虚拟环境、数据库、图片或登录状态。

在项目根目录安装依赖：

```bash
# 安装前端依赖。
npm --prefix frontend ci

# 创建 Python 虚拟环境并安装锁定版本依赖。
python3 -m venv automation/.venv
automation/.venv/bin/python -m pip install -r automation/requirements.lock
```

没有 Chrome 时，可按 [automation/README.md](automation/README.md) 安装 Playwright Chromium 并修改浏览器配置。

为系统建立数据库与独立用户（密码自行设置）：

```sql
CREATE DATABASE hamlab CHARACTER SET utf8mb4;
CREATE USER 'hamlab'@'localhost' IDENTIFIED BY '<设置自己的密码>';
GRANT ALL ON hamlab.* TO 'hamlab'@'localhost';
```

创建本机 `.env`，例如新安装 MySQL 使用默认 3306 时：

```dotenv
DB_URL="jdbc:mysql://127.0.0.1:3306/hamlab?useUnicode=true&characterEncoding=UTF-8&serverTimezone=UTC"
DB_USER=hamlab
DB_PASSWORD='replace-with-your-local-password'
```

构建和启动后端，使用自己安装的 Java 21，不使用当前 Mac 的 `.tools` 路径：

```bash
# 确认 java -version 为 Java 21，必要时先配置 JAVA_HOME。
mvn -f backend/pom.xml package

set -a
source .env
set +a
export STORAGE_DIR="$PWD/data"
export BROWSER_DIRECTORY="$PWD/automation"
export BROWSER_PYTHON="$PWD/automation/.venv/bin/python"
java -Djava.awt.headless=true -jar backend/target/hamlab-1.0.0.jar
```

再在另一个终端执行 `npm --prefix frontend run dev`。新机器自行启动其 MySQL 服务；不要直接使用本机快速启动部分的 `.tools/mysql-data` 命令初始化新数据库。

Windows 的虚拟环境解释器是 `automation\.venv\Scripts\python.exe`，将 `BROWSER_PYTHON` 设为实际绝对路径。本文启动命令以 macOS/Linux shell 为准，Windows 部署尚未实测。

## 9. CLI、HTTP 与 Docker

### 独立 CLI / HTTP

完整参数、缺陷类型映射及调用示例见 [automation/README.md](automation/README.md)。可脱离 Java/Vue 使用 CLI，例如仅生成规划清单：

```bash
# 将原图路径替换为自己的文件；此命令不打开浏览器、不实际生图。
automation/.venv/bin/python automation/main.py \
  --source_image ./data/images/ham001.png \
  --defect_type date_missing \
  --count 1 \
  --output_dir ./dataset \
  --date_text 2026.09.24 \
  --plan-only
```

可选 HTTP 接口为 `POST /generate-defects`，异步返回任务编号；通过 `GET /jobs/{id}` 查询结果。该服务仅监听本机并要求进程令牌。使用 Java 页面时由 Java 管理，不要另启同端口服务。

### Docker

现有 Compose 支持图库、Java 队列和数据库，**不包含图形浏览器执行器**。完整网页账号生图优先使用本机部署。

先按 `.env.example` 配置 `DB_PASSWORD` 和 `MYSQL_ROOT_PASSWORD`，不要覆盖已有本机配置：

```bash
# 从项目根目录构建并启动。
docker compose up --build -d

# 停止容器并保留数据库卷。
docker compose down
```

前端映射到 `127.0.0.1:5173`。不要和本机前端同时占用该端口。Docker 数据库卷与当前 Mac 的 `.tools/mysql-data` 是两套独立数据。

## 10. 项目目录与数据保存

```text
generatePhone/
├── backend/                 # Java API、图片存储、队列、审核、导出
├── frontend/                # Vue 页面
├── automation/              # 基于上游改造的 Python 执行器、CLI、HTTP
├── config/defects.json       # 共享缺陷配置
├── scripts/                 # 手动回填等辅助工具
├── data/
│   ├── images/              # 接收的原图和生成结果
│   ├── thumbs/              # 独立缩略图
│   └── browser/             # 本机登录配置及执行器日志
├── dataset/                 # Python 候选数据集
├── .tools/                  # 当前电脑专用 JDK、MySQL 数据及开发日志
├── .env                     # 当前电脑的数据库配置，不提交
├── compose.yaml
├── ACCOUNT_WORKFLOW.md
├── CHANGES.md
└── VALIDATION.md
```

备份需要同时保存数据库、`data/` 和需要保留的 `dataset/`。登录目录和 `.env` 含本机私密配置，不属于可分发源码。

参考来源与许可记录：[automation/UPSTREAM.md](automation/UPSTREAM.md)。上游固定提交为 `832ed7ce50e3d10ed9db05c76e28a51ca7bd708d`。
