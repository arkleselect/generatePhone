# 上游来源

- Repository: https://github.com/matthewmiglio/chatgpt-image-batcher
- Commit: `832ed7ce50e3d10ed9db05c76e28a51ca7bd708d`
- 原作者：上游 pyproject.toml 中的 matt；保留原作者字段。
- 在该提交中未找到 LICENSE 文件；公开可读不等于已授予开源再分发许可。对外分发或商用前需核实授权，本项目不替上游声明许可证。

保留原来的 image_gen.py auth/generate CLI 和 tests/test_cli.py、test_prompts.py、test_e2e.py。src/browser.py 扩展配置、会话迁移和互斥；src/chatgpt.py 保留提交/等待/下载及异常流程并增加参考图和稳定性支持；src/prompts.py 保留 JSON/slug 工具并扩展工业提示词。新增模块围绕这些原有函数组织，不创建第二套浏览器驱动。
