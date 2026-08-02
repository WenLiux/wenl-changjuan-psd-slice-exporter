# WENL / 长卷 Logo 使用规则

## 强制规则

- 深色背景（当前客户端的 `#070B14` 及相近色）只使用 `logo-white.svg` 或 `symbol-white.svg`。
- 浅色背景只使用 `logo-black.svg` 或 `symbol-black.svg`。
- 禁止在深色背景上使用黑色 Logo。
- 禁止通过 CSS `filter`、`invert()` 或透明度临时改变 Logo 颜色；必须使用已经明确着色的 SVG 文件。
- Logo 保持原始比例，不拉伸、不裁切、不增加描边或外发光。

## 资源对应关系

- `branding/source/`：品牌方原始 A03、A06 与符号文件，只作为母版保存。
- `frontend/src/assets/brand/logo-white.svg`：当前深色客户端的标准组合标识。
- `frontend/src/assets/brand/logo-black.svg`：未来浅色页面使用。
- `frontend/src/assets/brand/app-icon.svg`：A06 应用图标母版，打包阶段再生成系统图标格式。

当前客户端不得引用 `logo-black.svg`。
