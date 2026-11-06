<h1 align="center">
  <img src="./folder/logo.svg" alt="logo" width="200">
  <br>Surfing<br>
</h1>

<h3 align="center">Magisk, Kernelsu, APatch</h3>

<div align="center">
    <a href="https://github.com/GitMetaio/Surfing/releases/tag/Prerelease-Alpha">
        <img alt="Android" src="https://img.shields.io/badge/Module Latestsnapshot-F05033.svg?logo=android&logoColor=white">
    </a>
    <a href="https://github.com/GitMetaio/Surfing/releases">
    <img alt="Downloads" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/GitMetaio/Surfing/data/stats.json">
</a>
</div>
<br>
<div align="center">
    <a href="./README.md">English</a> | <strong>简体中文</strong>
</div>

---

本项目为 Clash/mihomo 的 [Magisk](https://github.com/topjohnwu/Magisk) 、 [Kernelsu](https://github.com/tiann/KernelSU) 、 [APatch](https://github.com/bmax121/APatch) 模块。支持 REDIRECT（仅 TCP）、TPROXY（TCP + UDP）透明代理，支持 TUN（TCP + UDP）亦可 REDIRECT（TCP）+ TUN（UDP） 混合模式代理。

基于上游为集成式一体服务、开箱即用   
此适用以下人群：
- 懒癌
- 小白

项目主题及配置仅围绕 [Clash/mihomo.Meta](https://github.com/MetaCubeX/Clash.Meta)  

本模块需在 Magisk/Kernelsu 环境进行使用，如果你不知道如何配置所需环境，你可能需要像 ClashForAndroid、v2rayNG、surfboard、SagerNet、AnXray 等应用程序。  

[Windows 用户](https://github.com/GitMetaio/SurfingWin)

# Surfing用户声明及免责

欢迎使用 在使用本项目前，请您仔细阅读并理解以下声明及免责条款。通过使用本项目，即表示您同意接受以下条款和条件。以下简称 **Surfing**

## 免责声明

1. **本项目是一个开源项目，仅供学习和研究之用，不提供任何形式的担保。使用者必须对使用本项目的风险和后果负全部责任。**

2. **本项目仅为简化 Surfing 对 Clash 服务在 Android Magisk 环境中的安装和配置提供便利，并不对 Surfing 的功能和性能做出任何保证。如有任何问题或损失，本项目开发者概不负责。**

3. **本项目 Surfing 模块的使用可能会违反您所在地区的法律法规或服务提供商的使用条款。您需要自行承担使用本项目所带来的风险。本项目开发者不对您的行为或使用后果负责。**

4. **本项目开发者不对使用本项目产生的任何直接或间接损失或损害负责，包括但不限于数据丢失、设备损坏、服务中断、个人隐私泄露等。**

## 使用须知

1. **在使用本项目 Surfing 模块前，请确保您已经仔细阅读并理解 Clash 和 Magisk 的使用说明和相关文档，并遵守其规定和条款。**

2. **在使用本项目之前，请先备份您的设备数据和相关设置，以防发生意外情况。本项目开发者不对您的数据丢失或损坏负责。**

3. **请在使用本项目时遵守当地的法律法规，并尊重其他用户的合法权益。禁止使用本项目进行任何违法、滥用或侵权的行为。**

4. **如果您在使用本项目时遇到任何问题或有任何建议，欢迎您向本项目开发者反馈，但开发者对于解决问题和回应反馈没有义务和责任。**

请您在明确理解并接受上述声明及免责条款后，再决定是否使用 Surfing 模块。如果您不同意或无法接受上述条款，请立即停止使用本项目。

## 法律适用

**在使用本项目的过程中，您须遵守您所在地区的法律法规。如有任何争议，应依照当地法律法规进行解释和处理。**

## 安装

- 从 [Release](https://github.com/GitMetaio/Surfing/releases) 页下载模块压缩包，然后通过 Magisk Manager 或 KernelSU Manager 或 APatch 安装
- 各版本变化 [📲日志.log](changelog.md)

## 卸载

 - 从 Magisk Manager 、Kernelsu Manager 、APatch 应用卸载本模块即可 [👉🏻铲屎流程](https://github.com/GitMetaio/Surfing/blob/main/uninstall.sh#L3-L4)

> 通过管理器卸载本模块，会卸载所有相应的服务数据，Web 等 SurfingTile 磁贴应用数据

## Group Telegram

<a href="https://t.me/Surfingbox">
  <img src="./folder/Group.png" alt="Group" width="100">
</a>

## Wiki

<details>
<summary>1. 首次使用</summary>

- 首次安装模块完成后，**请先**于 `/data/adb/box_bll/clash/config.yaml` 添加你的订阅地址，或者通过桌面 App(**注意: SurfingTile且持有Root才能操作**)，随后需手动重启设备一次
- 设备重启后，桌面打开 **SurfingTile App** 即可开始使用
- 可能因网络原因不会自动下载完全部 **规则**/**订阅**，请至面板手动刷新一下
- 如遇订阅无法加载请尝试切换配置里面的 **Ua**
- 如上述失败，确保你的网络环境正常

- SurfingTile App：
    - 可用于通过菜单 → 配置覆写 → 填写订阅
    - 用于便携浏览及管理后台路由数据

> 如遇面板显示内容异常 / 或内容无法显示  
需通过 Google play 商店更新 com.google.android.webview 组件版本

</details>

#

<details>
<summary>2. 控制运行</summary>

- 可通过 WiFi SSID/MAC 网络控制启停
- 可通过模块开关进行 关闭/开启 控制运行  
  `操作实时生效无需重启`
- 可向系统状态栏添加模块的控制开关磁贴  
  `如已安装SurfingTile`

</details>

#

<details>
<summary>3. 路由规则</summary>

- GitHub Actions 自动构建  
  路由规则全系在线订阅，保证规则最新

> 24小时自动更新

</details>

#

<details>
<summary>4. 后续更新</summary>

- 如果你全部使用默认配置，更新将是无感
- 支持在客户端中在线更新模块，更新后无须重启，但仍需建议重启
- 更新时配置文件会备份至
   - `config.yaml.bak`
- 更新时会备份旧文件用户配置，至
   - `box.config.bak`
- 更新时会自动提取你的订阅地址并备份，至
   - `proxies/subscribe_urls_backup.txt`
   - 自动提取备份并恢复至新配置中，适用于使用默认配置文件

> Ps：主要跟随上游更新，及下发一些配置

</details>

#

<details>
<summary>5. 使用问题</summary>

### 代理特定应用程序(黑白名单)
- 代理所有应用程序，除了某些特定的应用外，那么请打开 `/data/adb/box_bll/scripts/box.config` 文件，修改 `proxy_mode` 的值为 `blacklist`（默认值），在 `user_packages_list` 数组中添加元素，数组元素格式为`id标识:应用包名`，元素之间用空格隔开。即可**不代理**相应安卓用户应用。例如 `user_packages_list=("id标识:应用包名" "id标识:应用包名")`

- 只代理特定的应用程序，那么请打开 `/data/adb/box_bll/scripts/box.config` 文件，修改 `proxy_mode` 的值为 `whitelist`，在 `user_packages_list` 数组中添加元素，数组元素格式为`id标识:应用包名`，元素之间用空格隔开。即可**仅代理**相应安卓用户应用。例如 `user_packages_list=("id标识:应用包名" "id标识:应用包名")`

安卓用户组id标识：

| 标准用户 | ID  |
| -------- | --- |
| 机主     |  0  |
| 手机分身 |  10  |
| 应用多开 | 999 |

> 通常你可以在`/data/user/`找到本机所有用户组id及应用包名

### Tun模式
- 默认关闭
- 使用黑白名单时需排除相应包名

> 如特殊需要可自行通过配置开启

### 路由规则
- 为大陆饶行
- 基本能满足大多数日常使用需求

> 在分流规则日益健壮的情况下 黑白名单意义不大

### 家宽落地（固定 SOCKS5 出口）

支持在 OpenAI、Linux.do 等业务组中选择 **家宽落地**。线路为：设备 → **落地前置**中选定的机场节点 → 购买的 SOCKS5 → 网站。普通业务保留原来的策略；“家宽”是模式名称，不验证商家的住宅属性或 IP 信誉。

1. 使用支持 `rematch` 的 mihomo 核心，本功能已用 **v1.19.33** 验证。安装器会先检查当前核心的兼容性；不支持时终止安装，不替换设备配置。升级安装沿用设备原有核心，需要先通过现有核心管理方式更新核心。
2. 在设备上编辑 `/data/adb/box_bll/clash/private/landing.yaml`。首次安装/升级时会初始化这个文件，默认拒绝连接。将文件中的 `proxies` 替换为下列内容，填写商家提供的连接地址、端口和账号，只保留一个节点：

   ```yaml
   proxies:
     - name: 家宽 SOCKS5
       type: socks5
       server: '商家提供的连接地址'
       port: 12345
       username: '用户名'
       password: '密码'
       udp: false
   ```

   连接地址不一定等于网站看到的出口 IP。用户名、密码使用单引号包围；值内的单引号写成两个单引号。普通 SOCKS5 不加密认证信息，前置应选可信的机场；仅当商家支持 SOCKS5 over TLS 时才增加 `tls: true`，并保留证书校验。
3. 重载配置或重启核心。在面板的 **落地前置**中选择一个具体机场节点；初始选项为拒绝连接，必须手动选择。这里独立于“总模式”，只读取原有三个订阅，不包含家宽出口和直连。供应商重命名/删除节点时，要复核前置选择。运行中若 provider 更新失败，mihomo 会保留内存中的旧账号；删除或清空文件不会立即停用旧账号，停用时应改回 `reject` 示例并完整重载配置或重启核心。
4. 在 **OpenAI** 等需要固定出口的业务组中选择 **家宽落地**。普通业务无须改动。`家宽·TCP通道` 和隐藏的 `家宽·出口` 是内部连接项，无须手动配置。`profile.store-selected` 保留组选择。`DNS连接` 不提供家宽选项，因为 DNS 上游直接拨号不经过业务子规则；DNS 上游继续使用该组原来的选择。
5. 保持核心为 **Rule（规则）模式**。测试目标业务的连接链应包含家宽出口和所选前置；使用 IP 检测网站时，也要把该网站实际命中的业务组切到家宽，否则测到的是其他策略的出口。更换前置后再次确认最终 IP 相同，并检查晚高峰和长连接表现。

落地的 TCP 认证/连接失败时不会自动退回机场或直连。选择家宽的业务会在独立子规则内拒绝 **全部 UDP（包括 QUIC）**，避免不支持 UDP 时继续匹配普通规则；支持回退的网页改用 TCP，语音、游戏等依赖 UDP 的功能可能不可用。切回其他策略后不再施加这项限制。不要绕过 `家宽落地` 直接选择内部出口，也不要在私有文件中加入直连或其他节点类型。

此行为只覆盖运行中的核心在 Rule 模式下、实际匹配到该业务组的请求。自定义放行、GoogleFCM 等更早的规则仍优先生效；相关登录域名若命中另一个组，也需选择同一落地。全局/直连模式、停用模块、系统旁路和未纳入规则的流量不受此功能保护。IPv6 请求经同一 SOCKS5 发送时，商家的远端解析/出站仍可能采用不同地址，最终 IPv4/IPv6 是否一致需要实测。

前置选择优先考虑整条链路的稳定性和供应商可信程度，节点列表的测速不等于“设备 → 前置 → 落地 → 网站”的完整测试，也不能衡量 IP 信誉。更换前置可能中断已有连接；最终 IP 是否保持不变由 SOCKS5 服务商决定。

**升级与账号保留：**

- 安装器仅在私有文件不存在时初始化，重复升级不会覆盖账号；目录权限为 `0700`，账号文件为 `0600`。
- 使用新默认配置时会恢复订阅，并补回家宽 provider 引用。已有家宽配置选择“保留我的配置”时也能继续引用原账号。
- 首次从没有家宽功能的旧配置升级，请选择“使用新默认配置”。若选择完整保留旧配置，会原样保留，账号示例仍会部署，但不会自动给旧配置添加家宽功能。
- 源码中的 `landing.example.yaml` 只有占位配置。真实账号只填写到设备私有文件；Git 和构建 ZIP 均排除 `box_bll/clash/private/`。备份整个设备配置目录时，该文件仍可能被一起备份。

开发验证可运行 `python tests/test_landing.py --mihomo /path/to/mihomo --shell /path/to/ash --busybox /path/to/busybox`（需要 Python 3.10+ 和 PyYAML，以及主机平台的核心/BusyBox）。测试只使用本地模拟前置、认证 SOCKS5 和目标服务，安装测试将设备路径映射到临时目录并模拟 Android API；不代表 Android 防火墙、实际机场、SurfingTile 覆写或购买的出口已经通过实机验证。复现方法见 [测试说明](tests/README.md)。

### 面板管理
- Magisk字体模块

> 可能会影响页面字体正常显示

### 局域网共享
- 开启热点让其它设备连接即可
- Tun 网关: `198.18.0.0`

> 其它设备若访问控制台后端: `http://当前WiFi/Tun网关:9090/ui`

### Host文件
- 无需挂载：删除该文件即可
- 重新挂载：在 **etc文件夹** 新建一个即可
- 所有修改均实时生效
- 更新/安装时可通过音量键 上(**挂载**) 下(**卸载**) 选择

> 域名本地IP重定向，强制绑定

</details>

#

<details>
<summary>6. SurfingTile</summary>

### APP Service
### 📱设备要求
> 支持 Android10+

- 需要工作在**系统空间**，并且持有 **Root** 权限

- ~~对于 **KSU** 用户，则需要安装 **"元模块"** 才能拥有挂载权限~~ `com.github.surfing v6.0.0 已独立`
- 磁贴全程围绕 **Clash API** 工作，请检查 API 设置是否正确
  - **路径:** → 主页设置 → 更多设置 → 端口设置

### 隐藏彩蛋
> 通过长按首页图标 开启/关闭 **金牌特权**

- 预览
  ![程序界面](folder/SurfingTilePreviewImage.png)

</details>

---

<a href="./LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/GitMetaio/Surfing.svg">
</a>

## 致谢

<div align="center">
  <a href="https://github.com/CHIZI-0618">
    <img src="https://github.com/CHIZI-0618.png" width="100" height="100" alt="CHIZI-0618">
    <br>
    <strong>CHIZI-0618</strong>
  </a>
</div>

<div align="center">
  <p> > 感谢为本项目的实现提供了宝贵的基础 < </p>
</div>