# 家宽落地验证

安装 Python 3.10+、PyYAML，并准备主机平台的 mihomo 与 BusyBox。核心需要支持 `rematch`，当前验证版本为 v1.19.33。Windows 可使用 Git Bash 或 BusyBox 的 `ash.exe`；实际安装器使用随模块提供的 Android BusyBox。

```sh
python tests/test_landing.py --mihomo /path/to/mihomo --shell /path/to/ash --busybox /path/to/busybox
```

不传 `--busybox` 时跳过完整安装脚本模拟测试；其余测试仍执行。测试不依赖 Git HEAD，因此提交之后仍能复现旧配置升级。所有代理账号、DNS、TCP/UDP 服务均为本机测试数据，外部订阅/规则替换为本地数据，临时文件与核心进程在测试结束后清理。

覆盖首次安装、重复升级、旧配置两种保留选择、账号保留、旧核心提前阻止安装、权限设置路径、订阅恢复、配置修补失败时保留原文件，以及真实核心中的链式认证、前置切换/故障/删除、账号重载、缺失或错误账号、默认策略和选择记忆、UDP 拒绝、IPv6 目标、DNS 独立拨号。

安装模拟会运行 `customize.sh` 和 `box.landing`；Android 包管理、监听、权限属主/SELinux 操作和 BusyBox 链接部署使用测试替身。Windows 文件权限检查不能替代 Android 的 UID/GID、模式位和 SELinux 实测。真实机场、购买的出口、透明代理、设备网络切换和 SurfingTile 配置管理仍需设备验证。

建议检查新增代码：

```sh
shellcheck -s sh box_bll/scripts/box.landing build.sh
shfmt -d -i 4 -ci -sr -ln posix box_bll/scripts/box.landing
ruff check tests
ruff format --check tests
git diff --check
```

`customize.sh` 还需运行 ShellCheck 与 BusyBox `ash -n`；ShellCheck 的原有提示包含安装器读取的全局变量（SC2034）和 `print_lang` 的短路表达式（SC2015），与新增逻辑分别核对。

真实构建应在临时源码副本中执行，避免下载依赖和修改 `module.prop` 污染工作区。需要 curl、gzip、unzip、Info-ZIP zip 和基本 Unix 工具。可以显式固定版本，避免 GitHub API 限流并复现依赖选择：

```sh
MIHOMO_VERSION=v1.19.33 ZASH_VERSION=v3.30.0 SHORT_HASH=<source-commit> sh build.sh
```

不指定版本时仍使用 GitHub API 获取最新版本。curl 来自原有下载地址，需另记 SHA-256；同时记录核心、Zashboard、APK 和成品的版本/哈希。构建检查需验证 ZIP CRC、必需文件、SurfingTile 子包，以及私有账号、tests、IDE 文件和旧构建包没有进入 ZIP。应在临时副本放入虚拟账号，并预先创建带虚拟私密条目的同名旧 ZIP，验证重新构建也能清除旧条目。此验证不发布，也不修改模块更新渠道。
