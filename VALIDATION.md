# 验证记录

验证日期：2026-09-24。没有调用 OpenAI API，没有用真实账号生成测试图片，没有使用用户的工厂图片。

## 已实际运行

- `JAVA_HOME="$PWD/.tools/amazon-corretto-21.jdk/Contents/Home" mvn -f backend/pom.xml package -q`
  - Java 21 编译、Spring Boot 打包成功。
  - 7 个后端集成测试通过，0 failures / 0 errors。
  - 覆盖动态日期映射、首位/5和6位/5至8位缺失提示词、笛卡尔积数量、固定底图、草稿确认、暂停/取消、失败最多3次尝试、重启状态、账号串行等待及重复回填拦截、审核与导出、独立ROI、姿势来源继承。
- `npm --prefix frontend run build`
  - `vue-tsc -b` 类型检查与 Vite 构建通过。
  - 构建有 Element Plus 主包超过500KB的体积提示；不影响功能，未新增拆包插件。
- `python3 -m py_compile scripts/account_bridge.py`
  - 账号回填助手语法检查通过。
- 本机 MySQL 9.3 + Java 21 HTTP 联调：
  - Flyway V1、V2 实际迁移成功，health 返回 UP。
  - 上传原始字节保持一致、保存日期区域、底图审核、账号任务确认、等待队列、固定输入、结果导入、拒绝重复导入均通过。
  - 默认 ZIP 不包含未审核和拒绝图片；审核通过后的 ZIP 包含正确图片、root_source_id、人工 NG 标签及 JSONL 参数；不含凭据字段。
  - 数据库连接固定使用 UTC，生成时间按真实瞬间存储，前端按用户本地时区显示。
  - 联调用图印有 “TEST FIXTURE - NOT A REAL PRODUCTION PHOTO”，不是AI生图结果；测试结束后清理对应行和文件。
- Playwright 实际浏览器验证：
  - 1440×1000 与 820×900 页面查看、底图选择、第5/6位缺失预设、加入配置、任务计数、任务历史查看。
  - 科技蓝样式；无左上角名称/logo、无装饰性英文编号/口号。
  - 主内容区高度940、内容高度1130；侧边栏高度1000等于视口。
  - 主内容滚动190.5px后，window.scrollY=0、sidebar.scrollTop=0、sidebar.top=0：确认两者独立滚动。
  - 初始 favicon 404 已通过添加本地 SVG 修复。

## 未验证与边界

- 真实账号 Image 2.5 生图效果、账号额度、实际模型选择未验证：没有提供真实参考图。
- 系统不是无人值守的 ChatGPT 浏览器机器人。当前账号生图需要当前会话工具执行或用户手动回填；网页不直接调用对话工具。
- Docker Engine 在本机未启动，因此没有运行 compose 全容器部署；Dockerfile 和 compose 已提供，本机实际验证使用隔离的 MySQL 9.3。Flyway 对该较新数据库版本有支持范围提示，迁移与工作流已在此版本跑通。
- 没有独立配置 Lint 工具，不声称 Lint 已通过。

## 随机批量样本更新验证

- 再次运行 Java 21 下的 `mvn -f backend/pom.xml package -q`：9项测试通过，0失败、0错误。
- 新增覆盖80张随机任务：合法日期（含闰日）、缺陷位置不命中分隔符、具体程度已解析、来源保持固定、再生成不重新抽样；反向日期范围被拒绝；指定新日期也可替换底图日期。
- 旧7项工作流测试继续通过；历史参数未包含 randomization 时仍可读取，无数据库迁移。
- 运行 `npm --prefix frontend run build` 完成 TypeScript 检查和构建。
- 浏览器检查随机日期范围/格式、默认常用缺陷；旧逐字符选择已移除。本次未发起账号生图。

## 拖拽上传更新验证

- `npm --prefix frontend run build`：类型检查和构建通过。
- Playwright 使用实际文件 drop：图库拖入图片后打开上传弹窗，显示1张预览；弹窗拒绝txt文件；重复加入同一文件仍保留1张；移除后恢复0张并禁用上传。测试文件未提交到后端。
- 复用原有图片上传接口和校验，未修改后端或数据库。账号登录操作说明已加入设置弹窗。

## 原始参考图删除验证

- Java 21：`mvn -f backend/pom.xml package -q` 通过，10项测试，0失败、0错误。
- 新增覆盖：成功删除数据库记录及原图/缩略图、重复删除、已有任务引用、派生图引用、禁止删除姿势底图。
- `npm --prefix frontend run build`：TypeScript 检查与构建通过，仍有原有大包体积提示。
- 本地 MySQL 服务重启后通过 HTTP 上传专用测试图片并调用 DELETE，确认记录、原图和缩略图均已删除；未删除用户图片。

## 基于上游 Python 执行器的改造验证

- 实际 clone 上游并核实提交 `832ed7ce50e3d10ed9db05c76e28a51ca7bd708d`，未假设原文件结构。
- `automation/.venv/bin/python -m pytest automation/tests -m 'not e2e' -q`：29项通过，3项真实账号测试未执行；包含原有15项测试。测试涵盖10类提示词、原图逐次上传、上传/下载重试、超时只等待不重发、未知发送恢复、限额与取消、HTTP鉴权/路径、图片字节校验及跨域重定向拒绝。
- FastAPI TestClient 有一条 httpx 适配弃用提示，测试通过；没有为此新增重复HTTP依赖。
- Java21：`mvn -f backend/pom.xml package -q` 通过，13项测试，0失败、0错误；包括2040任务覆盖、批量删除回滚、共享缺陷模板、未知结果人工回填与防重复。
- `npm --prefix frontend run build` 通过：vue-tsc + Vite；保留原有包体积提示。
- 实际运行 CLI 的 `--plan-only`，使用专用测试夹具生成2个待执行任务和metadata/CSV/log，成功数量0，未调用生图。
- 系统保持关闭；本次没有启动Java/Vue/数据库/浏览器执行器，没有使用账号额度，没有验证真实网页选择器、参考图编辑效果或连续2000张。Docker与Windows未运行验证。
