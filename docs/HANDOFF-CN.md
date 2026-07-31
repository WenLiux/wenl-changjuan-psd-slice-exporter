# PSD/PSB 高保真切片导出器——项目交接说明

## 当前结论

项目已完成 0.1.0 版本开发、Windows 打包和最终验收，可直接用于：

- 读取 PSD/PSB 内嵌切片；
- 按原始宽度或指定宽度（例如 1440、750）导出；
- 避开 Photoshop 旧版“存储为 Web 所用格式”长边限制；
- 导出 PNG/JPEG；
- 保持全局缩放坐标一致；
- 自动生成并检查验证报告；
- 在需要时安全调用 Photoshop 高保真回退；
- 通过 Windows 桌面界面选择文件、拖放、预览、勾选切片并导出。

当前支持的用户成品为：

```text
release\PSD-PSB-Slice-Exporter-Windows-x64-v0.1.0.zip
```

解压后必须保持 `PSD-PSB-Slice-Exporter.exe` 与 `_internal` 文件夹在一起。

## 已完成阶段

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 0 | 旧方案审计、像素回归基线 | 完成 |
| 1 | V6/V7/V8 切片解析和类型模型 | 完成 |
| 2 | PSD/PSB 内嵌合成图读取 | 完成 |
| 3 | 原尺寸、防覆盖切片导出 | 完成 |
| 4 | 全局对齐的目标宽度缩放 | 完成 |
| 5 | 导出前检查和导出后验证 | 完成 |
| 6 | PNG/JPEG、ICC 和色彩处理 | 完成 |
| 7 | Photoshop 安全高保真回退 | 完成 |
| 8 | Windows 桌面 UI、后台任务和缓存 | 完成 |
| 9 | PyInstaller Windows 打包和成品验证 | 完成 |
| 10 | 最终验收和交付 | 完成 |

各阶段的详细报告位于 `docs`。

## 已验证结果

- 测试共收集 137 项。
- 带两个真实样本运行时：136 项通过，1 项按设计跳过。
- 最终打包程序分别成功处理 PSD 和 PSB，各导出 14 个切片。
- 从交付 ZIP 解压后的程序已再次按 1440px 导出并验证成功。
- 最终 GUI 能正常启动、响应并关闭。
- tkinterdnd2 打包运行库能正常加载。
- Photoshop COM 兼容组件已包含在 Windows 包中。
- 两个原始 Photoshop 文件在全部验收后哈希不变。

详细数据见：

```text
docs\stage-9-report.md
docs\stage-10-acceptance.md
```

## 回家后直接运行成品

1. 解压 `PSD-PSB-Slice-Exporter-Windows-x64-v0.1.0.zip`。
2. 打开解压后的 `PSD-PSB-Slice-Exporter` 文件夹。
3. 双击 `PSD-PSB-Slice-Exporter.exe`。
4. 将 PSD/PSB 拖进窗口，或点击“选择文件”。
5. 选择原始宽度，或输入 1440、750 等目标宽度。
6. 点击“开始导出”。

程序不会覆盖以前的导出结果，每次都会创建新的安全输出目录。

## 回家后继续开发

推荐环境：

```text
Windows 10/11 x64
Python 3.12 x64
Git
可选：Adobe Photoshop
```

如果使用交接包里的完整 Git 仓库包：

```powershell
git clone psd_slice_exporter-full-history.bundle psd_slice_exporter
cd psd_slice_exporter
```

创建开发环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-photoshop.txt
```

启动源码版桌面程序：

```powershell
.\.venv\Scripts\python.exe -m app.main
```

运行普通测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

带真实样本运行回归测试：

```powershell
$env:PSD_SLICE_V8_FIXTURE = '你的路径\565656未标题-1.psd'
$env:PSD_SLICE_V6_FIXTURE = '你的路径\详情切片.psb'
.\.venv\Scripts\python.exe -m pytest -q
```

## 重新构建 Windows 成品

创建独立发布环境：

```powershell
python -m venv .venv-release
.\.venv-release\Scripts\python.exe -m pip install -r requirements-build.txt
```

构建：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows.ps1
```

输出目录：

```text
dist\PSD-PSB-Slice-Exporter
```

## 关键安全约束

- 默认不启动或调用 Photoshop。
- Photoshop 回退只处理系统临时目录中的源文件副本。
- 回退完成后不保存临时文档、不退出 Photoshop。
- 调用前后会核对原文件 SHA-256、大小和修改时间。
- 外部修改过的源文件必须重新加载，缓存不会继续导出。
- “允许启动 Photoshop”“允许模式转换”“允许未验证合成图”不会保存，
  每次使用都需要重新明确选择。

## 当前已知限制

- 0.1.0 Windows 成品尚未进行数字签名，首次运行可能出现 SmartScreen
  提示。
- 当前正式交付形式是 onedir 文件夹 ZIP，不能只复制 EXE。
- Photoshop 高保真回退 V1 主要面向 8-bit RGB 文档。
- 单次第三方 PSD 解码、Pillow 缩放或图片编码内部不能即时中断；取消会在
  当前安全点完成。
- onefile 版本尚未作为正式交付物，当前 ZIP 已提供单文件下载体验。

## 后续可选方向

当前版本已经可用，下一阶段不是修复阻断问题，而是产品化增强：

1. 给 EXE 做正式代码签名和安装包。
2. 增加自动更新或版本检查。
3. 扩展更多色彩模式和 Photoshop 回退测试矩阵。
4. 增加批量处理多个 PSD/PSB。
5. 增加可保存的导出预设。
6. 增加 CI 中的 Windows 打包和签名流程。
7. 根据真实用户反馈调整 UI 文案和默认值。

## 给新的 Codex 任务使用的开场说明

可以把下面这段直接发给新的 Codex：

```text
请先阅读 README.md、docs/HANDOFF-CN.md、
docs/stage-9-report.md 和 docs/stage-10-acceptance.md。
这是 PSD/PSB 高保真切片导出器 0.1.0，阶段 0-10 已完成。
不要修改或覆盖 samples 中的原始 PSD/PSB；涉及真实样本时先后核对
SHA-256。先运行测试并查看 git status，再继续我接下来提出的功能。
```
