# 从上游版切换到 AstraSolis 定制版

需要手动覆盖安装一次定制包，之后模块管理器才会读取 Fork 的稳定更新渠道。修改 GitHub 上的清单不会改变已经安装的上游模块。模块 `id=Surfing`、`/data/adb/modules/Surfing` 和 `/data/adb/box_bll` 保持不变，可以覆盖安装；**不要先卸载**，卸载脚本会删除服务数据。

## 切换步骤

1. **先备份。** 用可信的 Root 文件管理方式备份整个 `/data/adb/box_bll`，另存当前模块版本和可用的旧安装包。至少包含 `clash/config.yaml`、`scripts/box.config`、`clash/proxies/`、`clash/etc/`、`clash/cache.db`，以及已存在的 `clash/private/landing.yaml`。备份内含订阅和账号，只保存在你能访问的位置，不上传到仓库、工单或构建目录。安装器的 `.bak` 会在后续升级被覆盖，不能代替这份独立备份。
2. **核对设备核心。** 覆盖安装保留设备已有的 `/data/adb/box_bll/bin/clash`，不会用包内核心替换它。先通过你现有、可信的核心管理方式升级到支持 `rematch` 的 mihomo；本版验证基础是 **v1.19.33**。安装器会提前检查，不兼容则中止，不替换服务配置。包内 ARM64 核心用于全新安装；包内有新核心不意味着升级设备上的核心也变新。
3. **下载稳定 ZIP。** 打开 [AstraSolis/Surfing 稳定发布](https://github.com/AstraSolis/Surfing/releases/latest)，核对作者仓库、标签和 `SHA256SUMS`。首版目标是标签 `v7.8.4-astra.1` 下的 `Surfing_v7.8.4-astra.1_release.zip`，`versionCode=1654`。首次正式发布前该入口可能返回 404；不要把“Source code (zip)”或旧的 `Surfing_alpha_320a690.zip` 当作迁移包，旧包仍指向上游更新地址。
4. **在模块管理器覆盖安装。** 通过 Magisk Manager、KernelSU Manager 或 APatch 安装 ZIP。按提示选择语言、hosts 挂载方式和配置保留方式；从上游旧配置切换并希望获得全部定制功能时，建议选择音量下键 **“使用新默认配置”**。安装器尝试恢复原订阅、迁移下表网络设置，并保留私有家宽账号。音量上键 **“保留我的配置”** 会保留整个旧 YAML，不能自动给原来没有家宽、Linux.do 或 AI 分组的配置添加功能。无按键输入超时走默认选项，务必看安装日志。
5. **核对配置后重启设备。** 对照备份检查订阅、代理模式、应用名单、Wi-Fi/蜂窝控制、hosts、自定义规则和个人端口。首次缺少 Linux.do 等规则缓存时，需要联网让 mihomo 按 provider URL 下载，必要时在面板刷新。确认家宽账号仍在私有文件，Rule 模式下在“落地前置”选择具体机场节点，再把目标业务组切到“家宽落地”。最后手动重启，检查模块管理器显示 `Surfing (AstraSolis)`，模块属性中的更新地址为下方 Fork 地址。

```text
https://github.com/AstraSolis/Surfing/releases/latest/download/Surfing.json
```

下载后可在电脑用 `sha256sum <ZIP 文件名>`，或 PowerShell 的 `Get-FileHash -Algorithm SHA256 <ZIP 路径>` 与同一 Release 的 `SHA256SUMS` 对照。Actions 的 Alpha 下载是一个外层产物归档：解压后才得到可安装的模块 ZIP，不要刷入外层归档。

## 哪些数据会保留

| 内容 | 现有覆盖安装行为 | 切换后需要核对 |
| --- | --- | --- |
| 订阅 | 从 `# 订阅地址相关` 到带 `↑` 的 `profile:` 标记提取并恢复到新配置 | 标记被改动、结构特殊或提取失败时手工恢复；不要公开日志中的订阅 |
| 网络控制 | 只迁移 `box.config` 中安装器 `VARS` 列表里的设置 | 下方列表以外的值从 `box.config.bak` 逐项核对，不能整文件覆盖新脚本配置 |
| 旧 YAML | 备份到 `config.yaml.bak`；按键决定使用旧 YAML 还是新默认 | 旧 YAML 不自动新增定制策略；新默认会替换你自己写的其他策略、DNS、端口等 |
| 家宽账号 | `/data/adb/box_bll/clash/private/landing.yaml` 已存在时不覆盖 | 目录 `0700`、文件 `0600`，Root 所有；不存在时初始化拒绝连接示例 |
| hosts | 原文件备份为 `hosts.bak`，安装包默认 hosts 会被部署或按选择移除 | 自己添加的 hosts 需逐项恢复，并确认是否挂载 |
| 自定义规则和策略记忆 | 升级不整体替换 `clash/etc/`、`rules/`、`proxies/`、`cache.db` | 保留旧策略记忆不代表使用了新默认；广告组若仍记忆 `PASS`，需手动改为拒绝 |
| AI 默认规则 | 首次安装及覆盖升级部署十份模块维护的 `rules/AI-*.list`，这些默认文件会被更新 | 个人修改另存 `etc/` 并显式引用；旧 YAML 不自动引用新规则。各 AI 组默认 `总模式`，按需单独选择家宽或机场节点，详见 [AI 分流说明](AI-ROUTING.md) |
| 优选模式 | 部署默认模板与独立调度脚本；仅在缺失时初始化私有 JSON，保留 API Key、预算和历史记录；订阅从当前核心自动发现，忽略旧 `providers` 名称列表；已有优选组会经核心校验后定向迁移为自动收集 | 保留其他 YAML 内容，首次迁移另存 `config.yaml.preferred.bak`；原本没有优选组的配置仍需接入监听入口和分组。默认不探测，详见 [优选说明](PREFERRED.md) |

当前 `VARS` 是：`enable_network_service_control`、`bypass_via_iptables`、`enable_cellular_proxy`、`enable_wifi_proxy`、`enable_ssid_filter`、`enable_mac_filter`、`use_wifi_list_mode`、`blacklist_wifi_macs`、`whitelist_wifi_macs`、`blacklist_wifi_ssids`、`whitelist_wifi_ssids`、`ap_list`、`gid_list`、`user_packages_list`、`proxy_mode`、`proxy_method`、`ipv6`。例如个人端口、TUN 设备名、DNS 转发、IKE NAT-T 绕过、额外网卡规则等不在列表中，需对照备份恢复，并保持 Shell 与 mihomo 设置一致。安装器还会为 `ap_list` 补充 `swlan+`、`softap+`。

私有账号只写到设备 `clash/private/landing.yaml`。发布包只带 `landing.example.yaml` 占位配置；Git、源码快照、ZIP 和构建日志均不收集私有账号。备份整个设备目录仍会包含真实账号，不能把设备备份作为构建源码。

家宽仍要求 Rule 模式：设备 → 所选“落地前置” → 固定 SOCKS5 → 目标网站。目标业务的 UDP（含 QUIC）被拒绝；TCP 认证或连接失败不会退回机场或直连。普通业务、DNS 独立拨号和已有的旁路条件保持原行为。账号重载、前置切换、IPv4/IPv6 出口一致性和实际网络效果需要在自己的设备与服务商上核对，详见 [家宽配置说明](../README_CN.md#家宽落地固定-socks5-出口)。

## 更新机制的边界

| 组件 | 本次迁移后的更新方式 |
| --- | --- |
| Surfing 模块 | 模块管理器读取 Fork **已发布稳定版**附件中的清单，按数值 `versionCode` 比较；普通 main 提交不会推送稳定更新 |
| Alpha | 仅从 [Alpha Actions](https://github.com/AstraSolis/Surfing/actions/workflows/prerelease.yml) 主动下载并手动安装，产物保留 30 天，下载通常需要 GitHub 登录；仍指向稳定更新渠道 |
| mihomo | 包内版本由依赖锁固定；全新安装部署，覆盖升级沿用设备核心，需独立管理 |
| Zashboard | 包内版本由依赖锁固定；全新安装部署，现有覆盖升级不替换设备面板目录；`webroot/index.html` 只是跳转到本机 `9090/ui` |
| curl / BusyBox | 覆盖安装会复制包内版本；来源和哈希记录在 `build-info.json` |
| SurfingTile APK | 按仓库当前 `app/version/com.github.surfing/release.json` 验证包内 APK，安装器用 APK 自身的 `versionCode` 决定升级，不降级已有较新 APK |

**SurfingTile 内置更新并未迁移。** 当前分支只提供预编译 `com.github.surfing` APK 和清单；`folder/SurfingTile.tar.gz` 是旧的 `com.yadli.surfingtile` 源码，不能证明当前 APK 的更新逻辑。现有 APK 下载清单仍保留上游来源，也未修改 APK。切换后请通过模块管理器更新模块；App 内的模块下载、在线配置覆写等入口尚未核实，使用前备份，并检查是否会重新写入上游配置或缺少定制组。不要把模块更新渠道迁移当成 App 全部更新入口已迁移。

安装较新稳定版后沿用同一流程备份、覆盖安装和核对配置。Alpha 的代码号刻意低于对应目标稳定版，稳定版可以取代它；若要从 Alpha 手动退回稳定版，仍先备份配置。需要自动分发修复时发布更大的 `versionCode`，不要降低清单代码号或替换已发布 ZIP。
