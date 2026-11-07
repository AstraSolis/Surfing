<h1 align="center">
  <img src="./folder/logo.svg" alt="logo" width="200">
  <br>Surfing · AstraSolis Edition<br>
</h1>

<h3 align="center">Magisk, Kernelsu, APatch</h3>

<div align="center">
    <a href="https://github.com/AstraSolis/Surfing/releases/latest">
        <img alt="Stable" src="https://img.shields.io/github/v/release/AstraSolis/Surfing?label=Stable">
    </a>
    <a href="https://github.com/AstraSolis/Surfing/actions/workflows/prerelease.yml">
        <img alt="Alpha" src="https://img.shields.io/github/actions/workflow/status/AstraSolis/Surfing/prerelease.yml?branch=main&label=Alpha">
    </a>
    <a href="https://github.com/AstraSolis/Surfing/releases">
        <img alt="Downloads" src="https://img.shields.io/github/downloads/AstraSolis/Surfing/total">
    </a>
</div>
<br>
<div align="center">
    <strong>English</strong> | <a href="./README_CN.md">简体中文</a>
</div>

---

This project is a [Magisk](https://github.com/topjohnwu/Magisk), [Kernelsu](https://github.com/tiann/KernelSU), [APatch](https://github.com/bmax121/APatch) module for Clash/mihomo. It supports REDIRECT (TCP only), TPROXY (TCP + UDP) transparent proxy, TUN (TCP + UDP), and hybrid mode REDIRECT (TCP) + TUN (UDP) proxy.

This is a personal edition maintained by [AstraSolis](https://github.com/AstraSolis/Surfing), based on [GitMetaio/Surfing](https://github.com/GitMetaio/Surfing). Upstream authorship, source history and the [GPL-3.0 license](LICENSE) are retained. Upstream updates are reviewed before merging.

Custom features include **Linux.do routing**, **default ad blocking and rule priority adjustments**, and a **fixed authenticated SOCKS5 exit** with a separate upstream selector, UDP rejection, no fallback on connection failure, and private credentials preserved during upgrades. Existing selection history may retain ad-blocking `PASS`; check the panel.

Module managers follow this fork's stable releases. Alpha builds are for manual testing. Switching from upstream requires one manual installation of a new custom ZIP. See the [migration guide](docs/MIGRATION.md), [release maintenance guide](docs/RELEASING.md) and [custom changelog](changelog.md).

The project's theme and configuration focus on [Clash/mihomo.Meta](https://github.com/MetaCubeX/Clash.Meta).

This module needs to be used in a Magisk/Kernelsu environment. If you don't know how to configure the required environment, you might need applications like ClashForAndroid, v2rayNG, surfboard, SagerNet, AnXray.

# Surfing User Declaration and Disclaimer

Welcome to use Surfing. Before using this project, please carefully read and understand the following statements and disclaimers. By using this project, you agree to accept the following terms and conditions. Hereinafter referred to as **Surfing**.

## Disclaimer

1. **This project is an open-source project for learning and research purposes only and does not provide any form of guarantee. Users must bear full responsibility for the risks and consequences of using this project.**

2. **This project is only for the convenience of simplifying the installation and configuration of Surfing for Clash services in the Android Magisk environment. It does not make any guarantees about the functionality and performance of Surfing. The developer of this project is not responsible for any problems or losses.**

3. **The use of this projects Surfing module may violate the laws and regulations of your region or the terms of service of service providers. You need to bear the risks of using this project on your own. The developer of this project is not responsible for your actions or the consequences of use.**

4. **The developer of this project is not responsible for any direct or indirect losses or damages resulting from the use of this project, including but not limited to data loss, device damage, service interruption, personal privacy leaks, etc.**

## Instructions for Use

1. **Before using the Surfing module, please make sure you have carefully read and understood the usage instructions and related documents of Clash and Magisk and comply with their rules and terms.**

2. **Before using this project, back up your device data and related settings to prevent unexpected situations. The developer of this project is not responsible for your data loss or damage.**

3. **Please comply with local laws and regulations and respect the legitimate rights and interests of other users when using this project. It is forbidden to use this project for illegal, abusive, or infringing activities.**

4. **If you encounter any problems or have any suggestions when using this project, you are welcome to provide feedback to the developer of this project, but the developer is not obligated to resolve issues or respond to feedback.**

Please decide whether to use the Surfing module only after clearly understanding and accepting the above statements and disclaimers. If you do not agree or cannot accept the above terms, please stop using this project immediately.

## Applicable Law

**During the use of this project, you must comply with the laws and regulations of your region. In case of any disputes, interpretation and resolution should be carried out in accordance with local laws and regulations.**

## Installation

- Download `Surfing_<version>_release.zip` from this [fork's stable release](https://github.com/AstraSolis/Surfing/releases/latest), check its `SHA256SUMS`, and install through Magisk Manager, KernelSU Manager or APatch. Do not install GitHub's “Source code (zip)”.
- The first stable target is `v7.8.4-astra.1`, versionCode `1654`. The stable endpoint may return 404 until its first publication. The old `Surfing_alpha_320a690.zip` still follows upstream updates and does not migrate the channel.
- Back up `/data/adb/box_bll` first; keep backups and credentials private. Update the device's existing mihomo to a version supporting `rematch` (tested with v1.19.33). Upgrade installation retains the device core. Install over the existing module, choose the new default config to obtain custom groups, verify subscriptions/settings/credentials, then reboot. Do not uninstall first.
- [Alpha Actions](https://github.com/AstraSolis/Surfing/actions/workflows/prerelease.yml) offers manual test artifacts for 30 days, generally requiring GitHub sign-in. Extract the downloaded artifact and install the module ZIP inside, not the outer artifact archive.

## Uninstall

- Uninstall this module directly from **Magisk Manager / KernelSU Manager / APatch**  
  [Uninstall script](uninstall.sh). Uninstalling is not required to switch to this fork.

> Uninstalling this module via the manager will remove all related service data, including Web and SurfingTile tile app data.

## Upstream Telegram Community

<a href="https://t.me/Surfingbox">
  <img src="./folder/Group.png" alt="Group" width="100">
</a>

## Wiki

<details>
<summary>1. First Time Use</summary>

- After the module is installed for the first time, **please first** add your subscription URL to  
  `/data/adb/box_bll/clash/config.yaml`, or add it through the desktop App  
  (**Note: SurfingTile requires Root permission to operate**), then manually reboot your device once.
- After rebooting, open the **SurfingTile App** from the desktop to start using it.
- Due to network issues, **rules**/**subscriptions** may not be fully downloaded automatically; please manually refresh them from the panel.
- If the subscription fails to load, try switching the **Ua** in the configuration.
- If the issue persists, make sure your network environment is working properly.

- SurfingTile App:
    - Can be used to add subscriptions via Menu → Config Override → Fill in subscription
    - Used for portable browsing and managing backend routing data

> If the panel content is displayed incorrectly or cannot be displayed,  
please update the `com.google.android.webview` component through the Google Play Store.

</details>

#

<details>
<summary>2. Controlling Operation</summary>

- You can control start/stop via **WiFi SSID/MAC**.
- You can control service using the module toggle switch  
  `Changes take effect in real time, no reboot required`
- You can add the module's control tile to the system status bar  
  `If SurfingTile is already installed`

</details>

#

<details>
<summary>3. Routing Rules</summary>

- mihomo refreshes remote rules using their provider URLs and configured intervals (24 hours by default). Local custom rules remain in the device's `clash/etc/` directory.
- The fork adds Linux.do routing and retains upstream icons and third-party rule sources. Rule refreshes are independent of module releases.

The fork also supports a fixed authenticated SOCKS5 exit. Select an airport node in **落地前置**, then select **家宽落地** in a service group such as OpenAI. Credentials live only in `/data/adb/box_bll/clash/private/landing.yaml`; the installer preserves this file. This mode rejects UDP and does not fall back to a normal proxy on TCP connection failure. A core supporting `rematch` is required (tested with mihomo v1.19.33). See the [setup and upgrade instructions](README_CN.md#家宽落地固定-socks5-出口).

AI services have separate routing groups, including Gemini, AI Studio and NotebookLM ahead of ordinary Google rules. Each service defaults to `总模式` and can independently select `家宽落地` or an airport node using the existing service-group options. Ten reviewed local rule files ship with the module and are deployed on upgrade. Shared Google, GitHub and CDN parent domains are not routed to the residential exit as a whole. See [AI routing, traffic limits and migration](docs/AI-ROUTING.md).

Preferred modes share IP reputation reports across ALL and regional selections, while retaining each group's selected node. Enable probing in the device-only `clash/private/preferred.json`; ProxyCheck supports anonymous queries through each tested node, with an optional key. Existing IPQS settings remain supported. Daily reviews cover active exits and a few backups, with checks before selecting expired candidates. See [preferred-mode setup and limits](docs/PREFERRED.md).

</details>

#

<details>
<summary>4. Future Updates</summary>

- After one manual channel-migration installation, module managers check `https://github.com/AstraSolis/Surfing/releases/latest/download/Surfing.json`. Normal main pushes produce only Alpha artifacts.
- Make an independent backup before every upgrade. The installer creates `config.yaml.bak`, `box.config.bak` and attempts to restore the marked subscription block through `proxies/subscribe_urls_backup.txt`; only the selected network variables are migrated automatically.
- Keeping the old YAML does not add new custom groups. Choosing the new defaults requires checking personal DNS, ports, hosts and rules. Reboot and verify actual traffic after upgrading.
- mihomo, Zashboard and SurfingTile have separate update mechanisms. **APK built-in updates have not been migrated.** This branch has only the current APK binary and its manifest; App configuration overrides also need separate verification. See the [component update boundaries](docs/MIGRATION.md#更新机制的边界).

</details>

#

<details>
<summary>5. Usage Issues</summary>

### Proxy Specific Apps (Blacklist / Whitelist)

- To proxy all apps except certain ones, open `/data/adb/box_bll/scripts/box.config`,  
  set `proxy_mode` to `blacklist` (default), and add elements to the `user_packages_list` array.  
  The element format is `id:package_name`, separated by spaces.  
  These apps will **not** be proxied.  
  Example: `user_packages_list=("id:package_name" "id:package_name")`

- To proxy only specific apps, open `/data/adb/box_bll/scripts/box.config`,  
  set `proxy_mode` to `whitelist`, and add elements to the `user_packages_list` array.  
  The element format is `id:package_name`, separated by spaces.  
  Only these apps will be proxied.  
  Example: `user_packages_list=("id:package_name" "id:package_name")`

Android user group IDs:

| User Type       | ID  |
| --------------- | --- |
| Owner           | 0   |
| Phone Clone     | 10  |
| Multiple Apps   | 999 |

> You can usually find all user group IDs and app package names under `/data/user/`.

### Tun Mode
- Disabled by default
- When using blacklist/whitelist, exclude the corresponding package names

> Can be enabled or disabled manually via configuration if required.

### Routing Rules
- Optimized for Mainland China
- Meets most daily usage requirements

> With increasingly robust routing rules, blacklist/whitelist is becoming less necessary.

### Panel Management
- Magisk font modules

> May affect proper display of panel fonts.

### LAN Sharing
- Enable hotspot to allow other devices to connect
- Tun Gateway: `198.18.0.0`

> To access the backend console from other devices:  
> `http://<CurrentWiFi>/<TunGateway>:9090/ui`

### Host File
- No need to mount: just delete the file
- To remount: create a new one in the **etc folder**
- All changes take effect immediately
- During update/installation, you can use volume keys Up(**Mount**) / Down(**Unmount**) to choose

> Local IP redirection for domains, forced binding

</details>

#

<details>
<summary>6. SurfingTile</summary>

### APP Service
### 📱 Device Requirements
> Supports Android 10+

- Must run in **system space** and require **Root** permission
- ~~For **KSU** users, you need to install the **"Meta Module"** to obtain mount permissions~~ `com.github.surfing v6.0.0 is now standalone`
- The tile works entirely based on the **Clash API**, please check if the API settings are correct
  - **Path:** → Home Settings → More Settings → Port Settings

### Hidden Easter Egg
> Long press the home icon to toggle **Gold Privilege**

- Preview
  ![App Interface](folder/SurfingTilePreview.png)

</details>

---

<a href="./LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/AstraSolis/Surfing.svg">
</a>

## Acknowledgements

<div align="center">
  <a href="https://github.com/CHIZI-0618">
    <img src="https://github.com/CHIZI-0618.png" width="100" height="100" alt="CHIZI-0618">
    <br>
    <strong>CHIZI-0618</strong>
  </a>
</div>

<div align="center">
  <p> > Thanks for providing valuable foundation for the implementation of this project. < </p>
</div>
