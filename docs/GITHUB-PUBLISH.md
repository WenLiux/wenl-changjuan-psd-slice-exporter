# GitHub 发布与维护清单

## 当前仓库

- 仓库：[WenLiux/wenl-changjuan-psd-slice-exporter](https://github.com/WenLiux/wenl-changjuan-psd-slice-exporter)
- 状态：公开
- 默认分支：`main`
- 当前稳定版本：`v0.3.1`
- 项目简介：WENL 长卷｜Windows PSD / PSB 高保真切片导出工具

## 公开内容边界

源码仓库不包含：

- 真实 PSD / PSB 测试文件；
- 客户设计素材、简历或照片；
- 用户名、联系方式和本机绝对路径；
- 构建缓存、虚拟环境和导出结果；
- 带本地路径的历史 UI 截图。

以下目录由 `.gitignore` 排除，不应手动添加：

- `.venv/`
- `.venv-release/`
- `build/`
- `dist/`
- `release/`
- `tmp/`
- `test-output/`

公开前应重新执行文本和二进制素材审计，尤其检查绝对路径、联系方式、密钥、
PSD / PSB、客户素材和截图中的 UI 文本。

## 当前 Release

[v0.3.1 正式发布页](https://github.com/WenLiux/wenl-changjuan-psd-slice-exporter/releases/tag/v0.3.1)

发布附件：

- `WENL-Changjuan-Windows-x64-v0.3.1.zip`
- `WENL-Changjuan-Windows-x64-v0.3.1.sha256`

发布正文统一维护在 [`docs/v0.3.1-release.md`](v0.3.1-release.md)。更新正文时，
同时确认下载链接、ZIP 大小、SHA-256 和附件名称仍然一致。

## 日常维护

1. 修改代码或资料前确认 `git status -sb`，不覆盖其他未提交改动。
2. 运行 `python -m pytest`。
3. 运行 `cd frontend && npm.cmd ci && npm.cmd run build`。
4. 检查公开内容是否包含本机信息或真实测试素材。
5. 更新版本号、发布说明和 Release 附件。
6. 推送后确认 GitHub Actions 通过，并核对远程提交与本地提交一致。

## 授权说明

源代码采用 [PolyForm Noncommercial License 1.0.0](../LICENSE)。它允许非商业目的的
使用、研究、修改和再分发；商业使用需要事先取得书面授权。再分发时必须保留
[NOTICE](../NOTICE)，WENL / 长卷名称、Logo、图标和品牌视觉资产不包含在代码许可证内。
详细边界见 [商标说明](legal/trademarks.md)、[商业使用说明](legal/commercial-use.md)
和 [第三方依赖声明](legal/third-party-notices.md)。
