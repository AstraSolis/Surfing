# 功能与发布验证

## 应用禁网

运行 `python tests/test_block.py --shell /path/to/ash`。测试在临时目录运行实际 `box.block` 与服务启停代码，使用模拟包列表和 IPv4/IPv6 防火墙，验证删除最后一项、保留其他名单、核心已退出时清理、核心重启恢复和模块停用清理。不会操作主机防火墙或 Android 设备；设备上的 UID、实际规则和停止后的连通性仍需实测。

## 优选模式

运行 `python tests/test_preferred.py --shell /path/to/ash --busybox /path/to/busybox --mihomo /path/to/mihomo --curl /path/to/curl`。测试使用真实核心、本机模拟代理和信誉接口，覆盖 Unicode/JSON 解析、实际出口查询、共享报告、独立地区选择、稳定保持、配额、限流、过期候选与 IPv6 风险。ProxyCheck 用例核对匿名请求经被测节点、带 Key 请求经管理连接、共享出口拒绝后不换来源重试、逐出口退避及全局故障暂停、未知字段不当零分、原始分与攻击记录分别处理、服务间缓存隔离和旧 IPQS 配置/账本兼容。测试副本将公共地址替换为回环地址，并跳过真实等待；间隔逻辑另用受控时钟验证。省略核心参数只运行解析及部分脚本验证，不表示端到端验证通过。

## AI 分流

准备 Python 3.10+、PyYAML 和主机平台的 mihomo v1.19.33：

```sh
python tests/test_ai.py --mihomo /path/to/mihomo
```

测试加载实际配置、十份本地 AI 文件和仓库自带的其他规则缓存，把远程 provider 改为文件读取，订阅替换为本机代理；所有测试主机和代理最终只连接回环地址，不访问真实 AI 服务或账号。先在普通出口核对每个服务组的真实命中，再逐个业务选择家宽，检查认证代理链；`rematch` 会替换连接记录中的原业务组，不能只用家宽连接的 `chains` 判断原始分组。

覆盖 Gemini/AI Studio/NotebookLM 分离、其余 AI 专用端点，普通 Google/YouTube/GitHub/微软服务和共享 CDN 不进入 AI、名称相似的假域名及 Azure 正则边界不误匹配、默认出口、业务间选择独立、直接选择家宽时的 UDP 拒绝和家宽认证失败不回退。每条 AI 规则至少有一个正向运行样例，并校验本地文件、provider、安装和打包清单一致。测试样例在 `fixtures/ai-routing.json`。不传 `--mihomo` 仅检查规则结构，其余运行测试会跳过，不代表完整验证。

下方家宽安装模拟同时检查首次部署十份规则、旧版本缺文件迁移、重复更新、保留旧 YAML/使用新默认两种选择、个人规则和旧缓存保留、包缺 AI 规则时提前中止、规则复制失败时保留现用 YAML，以及部分写入后失败仍保留旧规则并清理临时文件。发布测试检查 AI 文件与说明随包提供、缺规则的包被拒绝。目标 Android 登录、透明代理、语音、实时服务和网络切换仍需设备验收，见 [AI 分流说明](../docs/AI-ROUTING.md)。

## 家宽落地

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

## 发布链路

新增发布测试只用 Python 3.10+ 标准库。所有依赖下载和 GitHub 写操作使用离线替身，不访问真实账号或发布 API：

```sh
python tools/release.py check
python -m unittest discover -s tests -p test_release.py -v
ruff check tools tests
ruff format --check tools tests
shellcheck -s sh build.sh
actionlint .github/workflows/prerelease.yml .github/workflows/release.yml
git diff --check
```

覆盖稳定/Alpha 代码号及更新源、标签和清单不匹配、固定依赖/缓存损坏、APK 清单不一致、源码快照变化、ZIP 内容/校验和、凭据和旧条目排除、确定输入重复构建、未提交包禁止发布、远端标签校验、首次发布、版本号不递增、上传中断与草稿续传、已发布版本重跑不回退 latest、已有附件不覆盖、GitHub 未返回摘要时下载核验。它们不能证明 GitHub 真实权限、模块管理器更新行为或 Android 安装已经通过。

真实依赖构建必须在工作区外的源码快照中执行。新构建使用 Python 标准库，按 `release/dependencies.json` 下载固定 mihomo、curl、Zashboard 并校验 SHA-256；BusyBox 来自源码，SurfingTile APK 根据现有版本清单验证。

```sh
python tools/release.py snapshot /tmp/surfing-release-review
cd /tmp/surfing-release-review
sh build.sh --channel stable
sh build.sh --channel alpha
python tools/release.py verify dist/stable
python tools/release.py verify dist/alpha
```

Windows 也可直接运行副本中的 `python tools/release.py build --channel stable`；Git Bash 可用 `PYTHON` 指定解释器。旧的版本/提交环境变量会导致构建拒绝，依赖更新必须改锁文件并复核。输出的 `build-info.json` 记录实际源码、dirty 状态、工具链、关键依赖及包内文件哈希；`SHA256SUMS` 记录发布资产摘要。相同输入在同一工具链下重建应一致。

真实构建还应在快照内放入**虚拟** `box_bll/clash/private/landing.yaml`，预先创建带虚拟私密条目的同名旧 ZIP，验证新包没有这些条目，也没有 tests、IDE、工具和维护文件。检查 ZIP CRC、必需文件、ARM64 二进制与 SurfingTile 子包，比较包内配置、安装器和家宽脚本与当前源码。不要在快照创建后修改其输入文件；改动源码需重新导出。

若要验证构建失败、版本号错误和重复发布，可运行离线测试；不要调用 `tools/publish_release.py` 对真实仓库进行试发布。首次稳定发布及其设备验证仍须按 [发布流程](../docs/RELEASING.md) 获得对应授权。
