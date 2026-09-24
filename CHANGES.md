# 文件变更清单

原目录为空，无已有业务实现可复用。项目内部统一复用 Store 数据访问、Prompts 校验/模板、Images 文件处理和前端 api.ts 请求封装。没有改动原有公共接口。

最终执行方式为账号协作，不包含 API 生图适配器或密钥配置。界面为简洁科技蓝，导航与主内容独立滚动。

## 前端与界面

- `frontend/src/App.vue`
- `frontend/src/style.css`
- `frontend/src/api.ts`
- `frontend/src/types.ts`
- `frontend/src/main.ts`
- `frontend/src/components/AccountTask.vue`
- `frontend/src/components/BatchCreate.vue`
- `frontend/src/components/BatchHistory.vue`
- `frontend/src/components/ConfigDialog.vue`
- `frontend/src/components/Library.vue`
- `frontend/src/components/Review.vue`
- `frontend/src/components/ReviewDialog.vue`
- `frontend/src/components/RoiEditor.vue`

## 后端业务

- `backend/src/main/java/local/hamlab/AccountTasks.java`
- `backend/src/main/java/local/hamlab/Api.java`
- `backend/src/main/java/local/hamlab/Application.java`
- `backend/src/main/java/local/hamlab/Batches.java`
- `backend/src/main/java/local/hamlab/Exports.java`
- `backend/src/main/java/local/hamlab/HttpSafety.java`
- `backend/src/main/java/local/hamlab/Images.java`
- `backend/src/main/java/local/hamlab/Json.java`
- `backend/src/main/java/local/hamlab/Models.java`
- `backend/src/main/java/local/hamlab/Prompts.java`
- `backend/src/main/java/local/hamlab/ProviderConfig.java`
- `backend/src/main/java/local/hamlab/QueueWorker.java`
- `backend/src/main/java/local/hamlab/Store.java`

## 模板、迁移与测试

- `backend/src/main/resources/application.yml`
- `backend/src/main/resources/db/migration/V1__initial.sql`
- `backend/src/main/resources/db/migration/V2__account_receipts.sql`
- `backend/src/main/resources/prompts/common.txt`
- `backend/src/main/resources/prompts/defect.txt`
- `backend/src/main/resources/prompts/pose.txt`
- `backend/src/test/java/local/hamlab/WorkflowTest.java`
- `backend/src/test/resources/application-test.yml`

## 启动、配置与文档

- `.gitignore`
- `.env.example`
- `compose.yaml`
- `backend/pom.xml`
- `backend/Dockerfile`
- `backend/.dockerignore`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/public/favicon.svg`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `frontend/.dockerignore`
- `scripts/account_bridge.py`
- `ACCOUNT_WORKFLOW.md`
- `README.md`
- `VALIDATION.md`

本机 `.tools/`、`.env`、`data/`、构建产物及浏览器截图均为忽略文件，不是源码交付。验证结果与限制见 VALIDATION.md。

## 随机样本生成更新

- 新增 `backend/src/main/java/local/hamlab/RandomSamples.java`：合法日期与缺陷采样，排除日期分隔符。
- 修改 `Models.java`、`Batches.java`：逐图采样并冻结参数，兼容历史无随机配置记录，无数据库结构变更。
- 修改 `prompts/defect.txt`：先替换参考图旧日期，再施加唯一缺陷。
- 修改 `BatchCreate.vue`、`BatchHistory.vue`、`ReviewDialog.vue`、`types.ts`、`style.css`：日期范围与格式、移除字符选择、展示生成日期、复用蓝色表单和队列。
- 更新 `WorkflowTest.java`、`README.md`、`VALIDATION.md`。

## 拖拽上传与账号操作说明

- 新增 `frontend/src/components/ImageDropzone.vue`，统一拖拽/点击选择、文件校验、预览、移除与对象URL清理。
- 修改 `Library.vue` 和 `AccountTask.vue`，复用同一上传组件与原有请求接口；上传仍需确认。
- 修改 `ConfigDialog.vue`、`style.css`、`README.md`，说明 Codex / ChatGPT 登录位置和实际执行方式。
- 无后端接口或数据库变更。

## 原始参考图删除

- 修改 `Library.vue`：复用图库卡片和 API Client，新增删除按钮、确认弹窗和防重复提交。
- 修改 `Images.java`、`Api.java`：新增 DELETE 接口，锁定原图并检查任务和派生图引用；事务提交后清理原图和缩略图，清理失败记录服务端日志。
- 修改 `WorkflowTest.java`：验证成功删除、重复删除、任务引用、派生图引用和非原图拦截。
- 更新 `README.md`、`VALIDATION.md`；无数据库迁移或已有接口变更。

## chatgpt-image-batcher 接入（2026-09-24）

文件变更清单：

- 新增 `automation/UPSTREAM.md`，记录实际clone来源与提交；基于上游复制并修改 `src/browser.py`、`src/chatgpt.py`、`src/prompts.py`，保留 `image_gen.py`、示例及原测试。
- 新增 `automation/src/config.py`、`page_selectors.py`、`dataset.py`、`bridge.py`、`main.py`、`service.py`、依赖锁定和配置示例；新增离线恢复/HTTP/下载测试。
- 删除旧 `automation/worker.mjs`、`chatgpt.mjs`、`package.json`、`package-lock.json`，统一为上游 Python 执行器。
- 新增 `config/defects.json`、`DefectCatalog.java`；修改 `Prompts.java`、`Api.java`、`frontend/src/api.ts`、`App.vue`、`BatchCreate.vue`，共享15类缺陷定义，涵盖用户要求的10类。
- 修改 `BrowserRunner.java`、`application.yml`、`.env.example`、`ConfigDialog.vue`：Java启动Python，保留控制端口与网页操作入口。
- 修改 `AccountTasks.java`、`AccountTask.vue`、`BatchHistory.vue` 和 `WorkflowTest.java`：未知提交的已知结果可人工回填，自动回填和重复回填仍受拦截。
- 修改 `backend/pom.xml`、`backend/Dockerfile`、`compose.yaml`，新增 `.dockerignore`：共享配置随Java打包，修复Docker上下文；Docker不内置网页登录执行器。
- 更新 README、ACCOUNT_WORKFLOW、VALIDATION、.gitignore，新增 automation/README（按上游分析、改造、目录、代码、安装、CLI、HTTP、扩展八部分组织）。

复用：原Python函数契约、持久化配置与通用CLI，现有Java队列/回填/审核/导出，现有Vue图库和任务页面。旧任务的缺陷ID保持有效，无新增数据库迁移。现有V3顺序字段迁移继续使用。

兼容性：浏览器执行依赖本机Python和Chrome，独立HTTP需本机令牌；旧Node已发送回执的任务阻止自动重发。真实网页登录上传/生成/下载仍需单张联调，未声称网页端到端通过。
