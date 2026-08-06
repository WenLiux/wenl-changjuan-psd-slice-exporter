# 贡献指南

感谢关注 WENL 长卷。项目当前重点是 PSD / PSB 超长画布切片的稳定读取、
原始尺寸导出、缩放一致性和 Windows 桌面体验。

## 开始之前

- 使用 Windows x64 环境。
- 使用 Python 3.12 或兼容版本。
- 前端开发需要 Node.js 20 及 npm。
- 不要将真实 PSD / PSB、客户素材、简历、截图中的本地路径或个人信息提交到仓库。

## 本地验证

安装 Python 开发依赖：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

构建前端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

如果需要真实 PSD / PSB 回归测试，请通过 `PSD_SLICE_V8_FIXTURE` 和
`PSD_SLICE_V6_FIXTURE` 指向本机文件，不要复制到 Git 仓库。

## 提交代码时

- 保持修改范围聚焦，避免把格式化、临时文件和构建输出混入提交。
- 新增导出逻辑时，同时补充单元测试和验证报告。
- 修改 UI 时，确保真实控件、拖拽、键盘焦点和窗口缩放仍然可用。
- 涉及 Photoshop 的改动必须保持原文件只读和临时副本安全边界。
- 新增公开文档或截图前，检查是否包含用户名、绝对路径、客户素材或联系方式。

## Pull Request 建议

请在 PR 描述中说明：

1. 修改了什么，以及解决了什么问题；
2. 是否影响 PSD / PSB 解析、尺寸换算或导出格式；
3. 执行过哪些测试和构建命令；
4. 是否需要真实 Photoshop 或 Windows 环境复核。

提交前请确认 `python -m pytest` 和前端构建均通过。本项目源代码采用
[PolyForm Noncommercial License 1.0.0](LICENSE)。提交或再分发时请保留
[NOTICE](NOTICE) 和第三方依赖声明；WENL / 长卷品牌资产不属于代码许可证授权范围，
衍生版本应更换项目名称和视觉标识，详见 [品牌资产说明](docs/legal/trademarks.md)。
