# WENL 长卷项目维护说明

本文是面向维护者和贡献者的项目运行说明。当前正式版本为 `v0.3.2`，
公开下载和版本变化请以 README 与 GitHub Release 为准。

## 当前结论

WENL 长卷是 Windows PSD / PSB 高保真切片导出工具，支持：

- 读取 PSD / PSB 内嵌切片和合成图；
- 按原始宽度或指定宽度导出；
- 支持不切片的完整长图导出；
- 全局对齐的切片缩放与坐标换算；
- PNG / JPEG、透明背景、JPEG 质量和颜色策略；
- 文件选择与原生拖拽、预览、切片勾选和导出进度；
- 验证报告、取消任务和碰撞安全的输出目录；
- 可选的 Photoshop 高保真回退。

## 当前版本和发布物

- 稳定版本：`v0.3.2`
- 平台：Windows x64
- 发行形式：onedir 便携 ZIP
- 程序入口：`WENL-Changjuan.exe`
- 发布页：[WENL 长卷 v0.3.2](https://github.com/WenLiux/wenl-changjuan-psd-slice-exporter/releases/tag/v0.3.2)

解压后必须保持 EXE 与 `_internal` 文件夹的相对位置。程序不依赖开发服务器，
正式便携版运行时不需要互联网连接。

## 开发环境

推荐使用 Windows x64、Python 3.12、Git 和 Node.js 20。Photoshop 仅在测试或
明确使用高保真回退时需要。

创建 Python 环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

启动源码版：

```powershell
.\.venv\Scripts\python.exe -m app.main
```

构建前端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

真实 PSD / PSB 回归文件必须通过环境变量指向本机路径，不要复制到仓库：

```powershell
$env:PSD_SLICE_V8_FIXTURE = '本机测试文件路径'
$env:PSD_SLICE_V6_FIXTURE = '本机测试文件路径'
.\.venv\Scripts\python.exe -m pytest
```

## 构建 Windows 便携版

```powershell
python -m venv .venv-release
.\.venv-release\Scripts\python.exe -m pip install -r requirements-build.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows.ps1
```

输出目录：

```text
dist\WENL-Changjuan
```

打包时请保留 `WENL-Changjuan.exe`、`_internal` 和 `README-CN.txt` 的完整结构。

## 安全约束

- 默认不启动或调用 Photoshop。
- 原始 PSD / PSB 以只读方式使用。
- Photoshop 回退只处理系统临时目录中的源文件副本。
- 回退完成后不保存临时文档、不退出 Photoshop。
- 调用前后核对原文件 SHA-256、大小和修改时间。
- 启动 Photoshop、模式转换和未验证合成图均为单次授权，不会永久保存。
- 公开提交不得包含客户素材、个人信息、绝对路径或带路径的截图。

## 已知限制

- 当前正式交付为 Windows onedir ZIP，尚未提供安装向导和数字签名。
- Photoshop 高保真回退 v1 主要面向 8 位 RGB 文档。
- 单次第三方 PSD 解码、Pillow 缩放或图片编码无法在库内部即时中断，
  取消会在当前安全点完成。
- 真实 PSD / PSB 回归样本不随公开仓库分发。

## 维护顺序

1. 阅读 [项目文档导航](README.md) 和 [贡献指南](../CONTRIBUTING.md)。
2. 确认 `git status -sb` 并保持提交范围聚焦。
3. 运行 Python 测试和前端生产构建。
4. 检查公开内容是否泄露本机路径或测试素材。
5. 更新版本说明、Release 附件和 SHA-256。
6. 推送后核对 GitHub Actions、远程提交和发布页附件。
