# 项目文档导航

这里集中放置 WENL 长卷的使用、开发、视觉和发布资料。

## 面向使用者

- [项目首页](../README.md)：功能概览、下载、首次使用和命令行示例。
- [v0.3.1 发布说明](v0.3.1-release.md)：版本亮点、下载附件、校验值和安全边界。
- [Windows 打包报告](stage-9-report.md)：便携版结构与成品验证。
- [最终验收报告](stage-10-acceptance.md)：当前版本的验收结论和已知限制。

## 面向开发者

- [贡献指南](../CONTRIBUTING.md)：环境准备、测试、前端构建和提交规范。
- [阶段 0 审计](stage-0-audit.md)：旧版导出流程、数据流和兼容性基线。
- [阶段 1–7 报告](stage-1-report.md)：解析、合成图、缩放、验证、编码和 Photoshop 回退。
- [阶段 8 报告](stage-8-report.md)：桌面客户端、后台任务和可复用文档会话。
- [阶段 9 报告](stage-9-report.md)：Windows onedir 打包与解压验证。
- [UI 视觉重构规范](ui-visual-rebuild-spec.md)：布局、材质、光效和交互约束。
- [UI 重构报告](ui-redesign-report.md)：0.2.0 旧版 UI 的重构记录和验收说明。

## 品牌与发布

- [Logo 使用规则](../branding/guidelines/logo-usage.md)：深色背景、浅色标识和资源对应关系。
- [GitHub 发布清单](GITHUB-PUBLISH.md)：仓库内容、Release 附件和发布前检查。
- [UI 参考资料说明](ui-reference/README.md)：公开仓库中的隐私处理说明。

## 法律与授权

- [PolyForm Noncommercial License 1.0.0](../LICENSE)：源代码授权正文。
- [NOTICE](../NOTICE)：必需版权和品牌排除声明。
- [商标与品牌资产](legal/trademarks.md)：WENL / 长卷名称、Logo 和图标的使用边界。
- [商业使用说明](legal/commercial-use.md)：商业场景、非商业场景和授权联系说明。
- [第三方依赖声明](legal/third-party-notices.md)：运行时、构建时和 Web UI 依赖的核对入口。

## 当前状态

- 当前稳定版本：`v0.3.1`
- 目标平台：Windows x64
- Python 测试：`139 passed, 11 skipped`
- 前端生产构建：通过
- 发布包：GitHub Release 中的 Windows 便携版

阶段报告主要用于记录实现过程；如果阶段报告与当前首页或发布说明的数字、
文件名存在差异，应以当前版本的 README、发布说明和验收报告为准。
