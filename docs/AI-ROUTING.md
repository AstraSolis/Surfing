# 海外 AI 分流与家宽流量控制

本配置把 AI 专用域名放在 Google、Microsoft、GitHub 等通用规则之前，分别选择出口。规则审核日期为 **2026-11-06（Asia/Shanghai）**。公开域名资料不能证明所有客户端和账号都能正常使用，实际登录、地区限制、语音和媒体功能仍需设备验证。

## 使用方式

1. 在 Rule 模式使用新默认配置；不要把 Google、YouTube、Microsoft、GitHub 或漏网之鱼切到家宽来弥补单个 AI 域名缺失。
2. 各 AI 业务组默认选择 `总模式`，复用现有业务组的出口选项，可分别选择总模式、机场节点或家宽。
3. 按 [家宽配置说明](../README_CN.md#家宽落地固定-socks5-出口) 配置设备私有账号，在 `落地前置` 选择具体机场节点，再将需要家宽的业务直接设为 `家宽落地`，例如 `Gemini → 家宽落地`、`Claude → 家宽落地`。
4. 不需要家宽的业务保持 `总模式`，例如 `NotebookLM → 总模式`。`OpenAI` 使用相同的出口选项，各业务分别设置。切换后使用新连接核对；已建立的连接可能继续使用旧出口。

家宽模式的线路是设备 → 选定机场前置 → SOCKS5 出口 → AI 服务。它拒绝 UDP；TCP 连接失败不退回普通代理。各业务独立选择出口，切换 Gemini 不会联动 Claude 或 NotebookLM。Google、YouTube 等普通组保留各自的出口选项；仅需 AI 使用家宽时，无须调整它们。

现有 `rematch` 家宽通道会把连接记录中的策略链替换为子规则的最终出口。面板可能只显示 `家宽·出口`，无法据此直接按 Gemini/Claude 等原业务组统计流量。核对时结合目标主机、最终出口和家宽服务商用量；需要查看原业务组时，可以临时切回普通出口观察新连接。

## 分组和范围

| 策略组 | 本地规则文件（`box_bll/clash/rules/`） | 范围与边界 |
| --- | --- | --- |
| OpenAI | `AI-OpenAI.list` | ChatGPT、OpenAI API、服务专用静态资源与内容；不使用旧远程 `OpenAI.mrs` 大集合 |
| Gemini | `AI-Gemini.list` | Gemini 网页、移动端专用后端及 Workspace AI 专用后端；不包括普通 Gmail/Docs/Drive 前端 |
| AI Studio | `AI-AIStudio.list` | AI Studio、旧 MakerSuite、Gemini API；访问 `generativelanguage.googleapis.com` 的其他客户端也归此组 |
| NotebookLM | `AI-NotebookLM.list` | NotebookLM 前后端及独立入口；Drive/YouTube 导入涉及的共享服务保持原策略 |
| Claude | `AI-Claude.list` | Claude、Anthropic API、Claude Code 的认证、内容等服务自有域名；包括其自有下载子域 |
| Perplexity | `AI-Perplexity.list` | Perplexity、API，以及指定的 S3 上传桶和 Cloudinary 资源账户 |
| Grok | `AI-Grok.list` | Grok 独立站、xAI API、`grok.x.com`；不包括整个 X 或 Grokipedia |
| Microsoft Copilot | `AI-MicrosoftCopilot.list` | Copilot 专用域名；Bing/Edge/Office 上的共享接口保持普通策略 |
| GitHub Copilot | `AI-GitHubCopilot.list` | 专用推理接口、代码匹配接口和指定附件存储；GitHub 登录、通用 API、仓库下载保持原策略 |
| 其他AI | `AI-Other.list` | Poe、Mistral/Le Chat、OpenRouter、Groq；Groq 与 xAI 的 Grok 是不同服务 |

域名归类以实际请求的主机为准，不以客户端名称或使用的模型品牌为准。例如经 OpenRouter 调用 Claude 归 `其他AI`；经第三方网关、Azure 或 Vertex AI 访问模型，不自动归入原厂 API 策略。

## 节流边界

- 不使用 `google.com`、`googleapis.com`、`gstatic.com`、`googleusercontent.com`、`github.com`、`githubusercontent.com`、`bing.com`、`microsoft.com`、`x.com` 等公共父域覆盖 AI；具体的专用子域可以纳入。
- 不使用 Google IP/ASN 网段、整个 Google App 包名，或 `colab`、`generativelanguage` 之类宽泛关键词来识别 AI。Gemini 在 Android 上由 Google App 承载，整应用分流会扩大范围。
- `accounts.google.com`、`apis.google.com`、`lh3.googleusercontent.com`、`storage.googleapis.com`、`api.github.com`、通用 Cloudflare/Auth0/LiveKit/Cloudinary/S3 主机等保持原策略。Perplexity 等明确命名的专用存储主机例外。
- `geller-pa.googleapis.com`、`proactivebackend-pa.googleapis.com`、`optimizationguide-pa.googleapis.com` 等用途共享或证据不足的端点暂不加入。Google Code Assist、Flow、Jules、Antigravity、Colab 和模型仓库不因“与 AI 有关”自动进入家宽。
- 只匹配可确认的域名，不按 HTTPS URL 路径、页面用途或模型名分流。同一个主机上的普通业务、聊天、图片、音频或视频无法完全拆开；AI 自有下载域名、上传和生成内容也会消耗家宽流量。
- OpenAI 包含官方白名单中的精确主机 `cdn.openaimerge.com`；社区记录的 ChatGPT 异步 Azure 主机仅用带首尾锚点的正则匹配专用前缀和服务后缀，不包含其他 `webpubsub.azure.com` 租户。官方列出的共享 WorkOS、Stripe、Intercom 等依赖继续走普通策略。
- 独立 `sora.com` 不再由本地 OpenAI 规则覆盖，按后续普通规则分流；ChatGPT 内部同域媒体仍可能走 OpenAI。通用 LiveKit 主机和第三方统计不强制走家宽。语音功能还会受到前置 WebRTC 规则和家宽拒绝 UDP 的影响，不保证可用。
- 自定义放行、WebRTC、GoogleFCM、广告拦截仍早于 AI 规则。不要为了排查 AI 故障全局关闭广告拦截；先检查实际命中的规则。

若共享认证资源走普通代理后出现兼容问题，先记录失败主机、命中规则、客户端版本和用途，再决定是否添加精确例外。域名数据库和社区归类只是线索；不把 CDN 或 IP 的归属关系当作专用性的证明。

## 安装、升级和个人修改

这些 `.list` 是随模块维护的默认文件。首次安装随 `box_bll` 部署；覆盖升级只定向替换上述十份规则，不整体覆盖 `rules/` 或 `etc/`。安装器在替换设备文件前检查包内十份文件是否存在且非空，并在替换现用 YAML 前完成规则复制。每份规则先写同目录临时文件，写完才替换；复制失败则清理临时文件并中止，保留该规则旧文件和现用 YAML，不回滚此前已成功更新的规则。打包器也将它们列为必需项。它们不依赖首次联网下载，也不通过面板的规则刷新自动更新。

升级选择 **使用新默认配置** 才会得到新的组、provider 和规则引用。订阅按原备份标记恢复，私有家宽账号和策略选择缓存继续保留。选择 **保留我的配置** 会保留旧 YAML，不自动注入新组；即使新 `.list` 已部署，没有 provider/规则引用也不会被加载。旧 YAML 引用的 `OpenAI.mrs` 缓存和其他远程规则保持原状。

直接修改 `AI-*.list` 会在下次升级被默认内容替换。个人补充应放在独立的 `clash/etc/` 文件，并在个人 YAML 中显式添加 `type: file`、`behavior: classical`、`format: text` 的 provider，以及指向目标业务组的 `RULE-SET`。需要覆盖默认业务分流时放在 AI 规则之前。现有 `自定义规则.list` 指向的是 `特殊地址`，不是 AI 组；仅把域名写进去不会自动走 AI。选择新默认配置仍需手工恢复这些个人 provider 和规则引用。

从已发布版本升级、使用 SurfingTile 在线配置覆写或恢复旧备份后，都要检查实际生效的组和规则。当前仓库没有对应 APK 的源码，不能保证 App 的所有覆写路径会保留新增组。完整备份与迁移说明见 [MIGRATION.md](MIGRATION.md)。

## 来源与维护

各规则文件头部记录审核日期和来源。以下是资料用途，而不是把整页白名单直接导入：

| 来源 | 用途 |
| --- | --- |
| [Google Gemini API](https://ai.google.dev/api) | 确认 `generativelanguage.googleapis.com` API 端点 |
| [Gemini 隐私说明](https://support.google.com/gemini/answer/13594961?hl=en) | 确认 Android Google App 承载边界 |
| [OpenAI API](https://developers.openai.com/api/docs/quickstart)、[ChatGPT 网络要求](https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps) | 原厂 API、ChatGPT/Codex 的 HTTPS/WebSocket 和专用资源；帮助中心直接抓取返回 403，复核使用检索返回的官方正文，未把共享认证/CDN 白名单整体纳入 |
| [Claude Code 网络要求](https://code.claude.com/docs/en/network-config) | 区分 API、认证、内容、包仓库、下载和可选遥测 |
| [GitHub Copilot 白名单](https://docs.github.com/en/copilot/reference/copilot-allowlist-reference) | 区分 Copilot 专用接口与 GitHub 共享登录、API、仓库访问 |
| [Microsoft Copilot 要求](https://learn.microsoft.com/en-us/microsoft-365/copilot/microsoft-copilot-requirements)、[端点白名单](https://learn.microsoft.com/en-us/microsoft-365/copilot/add-copilot-endpoints-allowlist) | 确认专用入口；Office/Graph 共享认证、Edge 更新下载等保持普通策略，不整体导入 Microsoft 365 端点 |
| [Perplexity](https://docs.perplexity.ai/docs/getting-started/quickstart)、[xAI](https://docs.x.ai/developers/api-reference)、[Mistral](https://docs.mistral.ai/api)、[OpenRouter](https://openrouter.ai/docs/api_reference/overview)、[Groq](https://console.groq.com/docs/overview) | 原厂 API 与服务入口 |
| [v2fly domain-list-community](https://github.com/v2fly/domain-list-community)、[MetaCubeX meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | 社区发现的专用资源、旧入口和客户端后端；仍需设备确认 |
| [blackmatrix7 Gemini](https://github.com/blackmatrix7/ios_rule_script/blob/master/rule/Clash/Gemini/Gemini.list) | 交叉检查；未采用其共享 `apis.google.com` 及宽泛关键词 |
| [Netify Gemini 主机记录](https://www.netify.ai/resources/hostnames/gemini.google.com) | 辅助核对主机归属；不导入其 IP 集合 |

维护时先核对官方用途，再比较社区变化和设备连接记录；只补必要主机，更新文件头审核日期。不要直接覆盖为远程 `google-gemini` 或 `category-ai-!cn`，它们的分类范围更大，也可能继续变化。新增主机后同时补充正向/反向测试，确认其他 Google、GitHub、微软和共享 CDN 流量没有进入 AI 组。

## 验证范围

主机测试使用真实 mihomo 核心、本地规则和本机 SOCKS5/HTTP 服务，检查分组引用、实际命中、各业务独立选路、默认值、UDP 拒绝、错误账号时不回退，以及安装升级部署和文件保留。复现入口见源码仓库中的 `tests/README.md`；安装包不附带测试代码。它验证规则和代理链行为，不访问真实 AI 账号。

设备验收需另行完成：Gemini 网页和 Android 端登录/对话，AI Studio API、NotebookLM 上传，其他实际使用的 AI；同时访问 Google 搜索、YouTube、Drive、Photos、Play 和普通 GitHub，查看新连接命中及家宽用量。再检查 IPv4/IPv6、Wi-Fi/蜂窝切换、重载后的选择和语音/实时功能。只有规则语法校验通过不能证明这些业务可用。
