# v7.8.4-astra.1

- 首个 AstraSolis 定制稳定版，基于 GitMetaio/Surfing v7.8.4；保留原作者署名和 GPL-3.0 许可证。
- 模块管理器更新清单迁至 AstraSolis/Surfing 已发布稳定版的附件。稳定版 `versionCode=1654`，ZIP 和日志固定到版本标签；普通 main 提交只生成手动测试用 Alpha。
- 保留 Linux.do 独立分流、广告默认拦截与规则优先级调整，以及固定 SOCKS5 家宽落地、独立前置、UDP 拒绝、失败不回退和私有账号升级保留。
- 优选自动发现当前订阅和节点，兼容改名、新增、删除及旧 JSON 名称列表；已有优选组在升级时定向迁移，保留个人配置与账号。状态区分未启用、缺少 IPQS Key、无候选和发现失败。
- 构建固定 mihomo v1.19.33、Zashboard v3.30.0 和 curl 的源码版本及 SHA-256，验证预编译 SurfingTile v7.0.0；记录源码、依赖、包内文件和产物校验和。
- 稳定版在全部附件上传、校验完成后才公开；重复执行不会覆盖已发布附件或把 latest 回退。发布不再依赖下载统计或 data 分支。
- 上游用户须先手动覆盖安装一次定制 ZIP。升级沿用设备核心，安装前需确认支持 `rematch`；新功能建议选择“使用新默认配置”，再核对订阅与个人设置。详见 [迁移指南](https://github.com/AstraSolis/Surfing/blob/main/docs/MIGRATION.md)。
- SurfingTile 的 APK 内置更新和在线配置入口未迁移；上游待合入的 SurfingTile v7.1.0、应用断网功能不包含在本版。

# v7.8.4
### 📦 Sync Latest Branch
- Remove SurfingTile submodule
- Network filtering supports SSID/MAC matching

### 📱 SurfingTile v6.0.0
- New package `com.github.surfing`
- [View detailed changelog](https://raw.githubusercontent.com/GitMetaio/Surfing/refs/heads/main/app/version/com.github.surfing/release.json)

# v7.8.3
### 🛠️ Iptables
- Fix proxy list truncation caused by duplicate entries in `packages.list`
- Fix network loop issues when enabling hotspot in environments without public IPv6 support
- Refine GID filtering logic for TPROXY and REDIRECT modes

### 📦 Dependencies & Others
- chore: Update default Clash configuration
- chore(apks): Update SurfingTile to v5.38.1

# v7.8.2
- sync latest branch
- fix known issues and improve stability

# v7.8.1
- ipv6 intelligent management
- network filtering upgraded to ssids (mac) 
- fix known issues and improve stability

# v7.8.0
**Major changes:**
- add `apply_wifi_bypass()`, dynamically manage `net_bypass` chain
- hot switch inserts/deletes key chain rules directly, no service restart or touch disable needed
- introduce double debounce lock: timestamp check + lock file, prevents repeated triggers and concurrency during network fluctuations
- optimize state machine logic: accurately distinguish `disabled / bypassed / proxying / enabled` states
- refactor `rules_add()`: batch collect local ipv4/ipv6 addresses and apply rules at once, reducing iptables calls
- improve ssid and ip change detection, clearer logging

#### 1. Network switch mechanism deep refactor (iptables hot switch)
- switch method upgraded from module start stop to iptables hot switch, greatly improving response speed and stability

#### 2. Transparent proxy rules optimization
- clean up leftover rules, enhance rule robustness
- fix asymmetry in tproxy rule cleanup
- optimize ipv6 leftover rule cleanup logic
- refactor dns hijacking and redirect logic, improve reliability
- enhance overall logging for easier troubleshooting

#### 3. Startup and service optimization
- optimize boot sequence
- improve system firewall unblock logic
- inotifyd startup detection more reliable
- optimize hosts dynamic mounting process

#### Other updates
- config update: `config.yaml` add hosts rules, update ipv4 array, etc

### Tips
deep refactor around network and stability:
- faster and smoother network switch response
- improve ipv4/ipv6 dual stack compatibility
- reduce rule leftovers, concurrency conflicts, and unnecessary service restarts
- network filtering no longer relies on hard module service start stop

# v7.7.1
- remove the box toolbox from the working directory
- improve the stability of tun interface creation
- improve the iptables transparent proxy check
- optimize iptables performance limitations on the system kernel

# v7.7.0
- optimize iptables rule chain
- fix WeChat network loading lag issue
- introduce service process concurrency prevention to avoid potential memory leaks on some systems
