# AI 策略组 SVG 来源与维护

审核日期：2026-11-07（Asia/Shanghai）。这些图标用于识别策略组，与域名分流规则分别维护。

## 来源

| 策略组 | 文件 | 来源与核对依据 |
| --- | --- | --- |
| OpenAI | `OpenAI.svg` | 沿用现有 GitMetaio/Surfing 图标；本次 GET 确认上游 CDN 返回 SVG，与本地字节一致，未改图形 |
| Gemini | `Gemini.svg` | LobeHub `gemini-color.svg`；与 Gemini 官方首页引用的四色产品图标核对 |
| AI Studio | `AIStudio.svg` | Google 官方 AI Studio 产品标识；采用彩色图形，未采用图标库中的旧单色图形 |
| NotebookLM | `NotebookLM.svg` | NotebookLM 官网当前 `branding/v6/light_mode` 彩色 SVG |
| Claude | `Claude.svg` | LobeHub `claude-color.svg`；Claude 的橙色星形标识 |
| Perplexity | `Perplexity.svg` | LobeHub `perplexity-color.svg`；青色产品标识 |
| Grok | `Grok.svg` | LobeHub `grok.svg`；与 Grok 官网 favicon 中的图形核对，避免引入官网 SVG 的 foreignObject |
| Microsoft Copilot | `MicrosoftCopilot.svg` | Microsoft Adoption 的 Copilot 页面直接引用的官方 SVG；URL 中的日期不作为最新品牌版本的证明 |
| GitHub Copilot | `GitHubCopilot.svg` | GitHub 官方 Primer Octicons 的 `copilot-24.svg` 产品图标；区别于 Microsoft Copilot 的彩色标识 |
| 其他AI | `Ai.svg` | 复用现有上游通用机器人图标；配置 URL 本次 GET 返回有效 SVG |

LobeHub 文件来自 `@lobehub/icons-static-svg@1.102.0`，npm 元数据的源码提交为 `989535d6c13da2dec5a2937fe2789d4af4fdd8e0`。下载包通过其 SHA-512 integrity 校验后提取所需 SVG，没有安装或运行包脚本。LobeHub 与 GitHub Octicons 的 MIT 许可全文保存在 `AI-LICENSES.txt`；该许可不应被扩展解释为 Google、Microsoft 等其他官方品牌资源的许可。

Google 与 Microsoft 文件来自官网品牌资源，其下载文件未附带开源许可声明。保留来源与品牌归属，不将它们标注为 MIT。OpenAI 和通用机器人沿用已有仓库资源。

## 文件处理

- 八个新文件统一采用 `32 × 32` 画布；按图形的可见边界等比缩放并居中，不改变轮廓比例。只保留绘制所需元素及属性，移除布局用的 `1em` 尺寸与 CSS 继承依赖。
- Grok、GitHub Copilot 使用固定深色图形及浅色圆角底板，确保作为外部 SVG 图片时在浅色、深色背景上都可辨认。
- AI Studio 官方 SVG 包含矢量裁剪路径和四张内嵌 PNG 渐变图；保留路径和图像位置，将内嵌图片长边缩至 128 像素，适用于 16–32 像素的策略组图标。文件从 728245 字节缩为 60095 字节；它仍是带内嵌位图的 SVG，不称为纯矢量素材。没有外链图片。
- 其余新图标仅含矢量绘制内容。新增文件不包含脚本、事件属性、foreignObject 或外部字体/图片引用，渐变和裁剪仅使用文件内部 ID。
- Microsoft 官网路径包含 `2023/09`，审核时页面仍引用此文件；没有据路径日期或社区文件名声称它是最新品牌版本。

## 加载与发布

配置采用远程 SVG，与现有策略组的图标加载方式一致。八个新文件使用本 Fork 的 GitHub Raw URL；图标和配置需要同一次提交推送到 `main`，才能核对远程文件是否与本地一致。本次未预先请求尚未推送的新地址，避免把未发布状态误报为已可用。

抽查时上游 OpenAI、Ai 的 jsDelivr URL 返回 200；Fork 的既有 LinuxDO jsDelivr URL 返回 403，而 Fork 的 GitHub Raw Ai 文件返回 200，因此新增图标使用 GitHub Raw。HTTP 状态是本次观测，不能代表所有网络或未来缓存状态。

`app/icon/` 是源码仓库中的远程图标目录，不在模块 ZIP 运行文件清单中；不新增安装器复制逻辑。新增来源说明与许可文件也随源码保留。维护图标时核对面板显示、大小写、来源内容及 SVG 结构，不只查看文件扩展名。需要检查 Android 客户端显示时，仍须目标设备验证。

## 原始文件 URL 与 SHA-256

以下记录下载时的原始内容，便于发现官方地址或上游包之后的变化。工作区文件包含上述尺寸、背景和内嵌图像处理，因此其哈希不同。

### Gemini.svg

- 来源：https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.102.0/icons/gemini-color.svg
- 原始 SHA-256：`8ab0a9bafec11f7e69bcb9fc4ffd8f1bc927d1ddcbbb6ff36dee5ae8b5a9d602`

### AIStudio.svg

- 来源：https://www.gstatic.com/images/branding/productlogos/ai_studio/v1/192px.svg
- 原始 SHA-256：`84fea690c45abf339a983adcc9c9026741022b4e2b525786e11337f1b64f5c39`

### NotebookLM.svg

- 来源：https://notebooklm.google/_/static/branding/v6/light_mode/favicon/favicon.svg
- 原始 SHA-256：`0e369abeda7894c1d9762e9ae709c07d9007574ecc439fff95c675f9a7adf563`

### Claude.svg

- 来源：https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.102.0/icons/claude-color.svg
- 原始 SHA-256：`a3101f3047a119aa11825ad9369510f0c472428c8c52d420e31bc62db44a8364`

### Perplexity.svg

- 来源：https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.102.0/icons/perplexity-color.svg
- 原始 SHA-256：`8353f3ab20822f1a933224b0ea32cc39f0c32d5740f4af8c254b0f418e0a3a70`

### Grok.svg

- 来源：https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.102.0/icons/grok.svg
- 原始 SHA-256：`9175fc90c22655160231976c849f25a03b888d7cc0e04c5f1b987b659bb07c95`

### MicrosoftCopilot.svg

- 来源：https://adoption.microsoft.com/wp-content/uploads/2023/09/icon-copilot.svg
- 原始 SHA-256：`611f64330ec6126053d0f4c00c167c0dc11197d67fc0606e1c07582c20c8e523`

### GitHubCopilot.svg

- 来源：https://raw.githubusercontent.com/primer/octicons/main/icons/copilot-24.svg
- 原始 SHA-256：`eeafb3c2f333e04ccf7d031ae215f7adafaed4c6352556b0bf79496e048bcdd7`

## 品牌与官方页面参考

- LobeHub 图标库：https://github.com/lobehub/lobe-icons
- Gemini 官方首页：https://gemini.google.com/
- AI Studio 官方首页：https://aistudio.google.com/
- NotebookLM 官方首页：https://notebooklm.google/
- Grok 官方 favicon：https://grok.com/images/favicon.svg
- Microsoft Adoption Copilot：https://adoption.microsoft.com/en-us/copilot/
- GitHub Copilot 品牌说明：https://brand.github.com/brand-identity/copilot
