# 第三方依赖与声明

本项目包含或构建时使用第三方软件。第三方软件不因本项目采用 PolyForm Noncommercial License 1.0.0 而改变其原有许可证、版权声明或使用条件。发行或制作衍生版本时，请同时遵守各依赖的上游条款。

## 依赖清单来源

当前依赖声明位于以下文件，版本以这些文件和前端 lockfile 为准：

- Python 运行时：requirements.txt（customtkinter、Pillow、psd-tools、tkinterdnd2、pywebview）；
- Windows / Photoshop 适配：requirements-photoshop.txt（pywin32）；
- 构建工具：requirements-build.txt（PyInstaller、resvg-py 等）；
- Web UI：frontend/package.json 与 frontend/package-lock.json（React、React DOM、lucide-react、Vite、TypeScript 及类型包）。

每次发布前，应根据实际安装版本的包元数据、上游仓库和 lockfile 重新核对许可证，并在发行包中保留必要的第三方版权与许可文本。仓库不会把第三方依赖声明为 WENL 长卷自有代码。

## Adobe 与 PSD / PSB

Adobe、Photoshop、PSD 和 PSB 是第三方名称或格式相关权益。本项目不是 Adobe 官方产品，也不代表 Adobe 背书。使用 Photoshop 回退能力时，用户需自行持有合法的 Photoshop 安装和使用权限，并遵守 Adobe 许可及客户素材的相关要求。

如发现发行包缺少某个依赖的许可证或版权声明，请通过仓库 Issue 提交可复现的版本信息和来源链接；不要上传客户文件、个人信息或密钥.
