# GitHub 发布清单

## 源码仓库

上传当前 Git 仓库，不要手动添加以下目录：

- `.venv/`
- `.venv-release/`
- `build/`
- `dist/`
- `release/`
- `test-output/`

这些内容已由 `.gitignore` 排除。源码仓库不包含真实 PSD / PSB 测试文件。

## 建议仓库信息

- 仓库名：`wenl-changjuan-psd-slice-exporter`
- 简介：`WENL 长卷｜Windows PSD / PSB 高保真切片导出工具`
- 默认分支：`main`
- Release 标签：`v0.3.1`

## GitHub Release

创建 `v0.3.1` Release，并上传：

- `WENL-Changjuan-Windows-x64-v0.3.1.zip`
- `WENL-Changjuan-Windows-x64-v0.3.1.sha256`

Release 正文可使用 `docs/v0.3.1-release.md`。

## 发布前选择

创建远程仓库前需要确认：

1. 仓库是公开还是私有。
2. 是否添加开源许可证；未添加许可证时默认保留全部权利。
3. GitHub 账号或组织名。
