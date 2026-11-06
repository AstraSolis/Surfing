# AstraSolis 定制版构建与发布

本 Fork 保留 GitMetaio/Surfing 的历史、署名和 GPL-3.0 许可证，模块身份与设备目录不变。个人功能包括 Linux.do 分流、广告拦截调整和固定 SOCKS5 家宽落地。同步上游时按 [AGENTS.md](../AGENTS.md) 先获取、评估，再经确认合并；发行元数据不能直接被上游默认值覆盖。

## 版本和渠道

| 项目 | 来源或规则 | 首版例子 |
| --- | --- | --- |
| 基础版本 / 稳定代码号 | **只在 `module.prop` 维护** `version` 和 `versionCode` | `v7.8.4-astra.1` / `1654` |
| 稳定标签 | 与基础版本完全相同，标记最终审查的提交 | `v7.8.4-astra.1` |
| 稳定 ZIP | 从基础版本生成 | `Surfing_v7.8.4-astra.1_release.zip` |
| 包内显示版本 | 基础版本加渠道和提交前 7 位；兼容安装器的 SurfingTile 同步字段 | `v7.8.4-astra.1 (release-abcdef0)` |
| Alpha ZIP | 基础版本、alpha、提交前 12 位 | `Surfing_v7.8.4-astra.1_alpha_abcdef012345.zip` |
| Alpha 代码号 | 目标稳定代码号减 1，不为每次提交分配设备更新号 | 首版 Alpha 为 `1653` |
| 已发布更新清单 | Release 附件 `Surfing.json`，显示版本及代码号与包内完全一致 | 精确指向同一标签的 ZIP 和 `changelog.md` |
| 仓库根 `Surfing.json` | `python tools/release.py sync` 生成的预览，不是设备更新源 | 基础版本，不含尚未确定的构建提交后缀 |

模块更新入口固定为：

```text
https://github.com/AstraSolis/Surfing/releases/latest/download/Surfing.json
```

清单内部使用 `/releases/download/<具体稳定标签>/<准确附件名>`，不使用浮动 `latest` 下载 ZIP 或 main 分支日志。这样旧清单即使被缓存，也仍指向它对应的完整版本。首次稳定版发布前入口返回 404 属于尚未建立频道，不能回退上游。所有正式发布都必须附带这套资产，不能手工把缺少清单的其他 Release 标记为 latest。

[GitHub latest](https://docs.github.com/en/rest/releases/releases#get-the-latest-release) 排除 draft 和 prerelease。工作流在发布稳定版时显式设置 `prerelease=false`、`make_latest=true`，不依赖 GitHub 对 `-astra.N` 字符串的语义排序；模块管理器依据数值 `versionCode` 判断升级。每个后续稳定版的代码号必须大于**所有已发布稳定版**，与上游的代码号独立维护，不在合并时照抄。版本名也换新，例如 `v7.8.4-astra.2` / `1655`；升级上游基础版本后仍继续递增代码号。

Alpha 仅为 Actions artifact，不创建 Release、不创建或移动标签，不提供另一套自动更新 JSON。手动安装 Alpha 后模块仍跟随稳定频道：下一目标稳定版能覆盖它；若同一目标稳定版已发布，管理器可能立即提示回到稳定版。旧 `Prerelease-Alpha` Release 和附件保留原状，不再维护；`Surfing_alpha_320a690.zip` 仍带旧的上游更新入口。

## 维护与本地验证

1. 在当前 `main` 检查工作区和上游影响，保护未提交修改。维护 `module.prop` 的版本、代码号及 `changelog.md` 首个同名章节；其他历史章节保留上游来源。
2. 运行 `python tools/release.py sync` 生成预览，再运行 `python tools/release.py check`。工作流会拒绝预览过期、版本不匹配、代码号越界、无明确日志或依赖未固定等情况。不要手工另改 ZIP 名和 JSON 版本。
3. 运行 [测试说明](../tests/README.md) 中的发布链路测试及与实际功能修改相符的测试。构建工具只检查包结构和 Android ARM64 ELF 标识，不能在桌面执行 Android 核心来证明设备兼容；家宽运行验证使用主机版 mihomo，设备行为另测。
4. 在工作区外创建当前文件的源码快照，并在副本构建：

   ```sh
   python tools/release.py snapshot /tmp/surfing-release-review
   cd /tmp/surfing-release-review
   sh build.sh --channel stable
   sh build.sh --channel alpha
   python tools/release.py verify dist/stable
   ```

   目标目录必须尚不存在。快照复制已跟踪及未忽略的新源码，带原始提交、是否存在未提交改动、完整源码文件哈希清单，排除 Git 元数据和私有账号。Windows 可用 Python 3.10+ 直接运行副本中的 `python tools/release.py build --channel stable`，或为 Git Bash 设置 `PYTHON` 到可用解释器。不要使用设备 `/data/adb/box_bll` 作为源码。
5. 审查 `dist/stable/` 的五项资产：模块 ZIP、`Surfing.json`、`changelog.md`、`build-info.json`、`SHA256SUMS`。Alpha 只有其中四项，**没有更新 JSON**。输出目录必须为空或只含同一版本的资产；新版本用新目录。构建从源码清单选择运行文件，不打包 `.git`、工作流、开发工具、测试、IDE、旧 ZIP、维护规则和私有目录，只有迁移指南随包提供。

Python 构建工具只依赖标准库，`build.sh` 是入口包装，不再改写源码 `module.prop`。下载缓存默认在系统临时目录 `surfing-release-dependencies`，可通过 `--cache <目录>` 指定；每次使用都校验 SHA-256。ZIP 从零创建，固定条目顺序、时间戳和 Unix 权限；不会因更新旧 ZIP 留下已排除的私密条目。

### 依赖与构建记录

远程依赖统一在 `release/dependencies.json` 固定版本、URL 和 SHA-256。本版沿用已有测试版本：mihomo `v1.19.33`、Zashboard `v3.30.0`；curl `8.6.0-DEV` 固定到 `abadb8315e34f7bfa07b596e810617978f1b9984`，不再从可变 master 取文件。检测到旧的 `MIHOMO_VERSION`、`ZASH_VERSION`、`SHORT_HASH` 或 `isAlpha` 环境变量覆写时会拒绝构建；改锁文件、复核来源哈希并重新验证才是更新依赖的入口。

BusyBox 由源码仓库的二进制提供；SurfingTile 由 `app/version/com.github.surfing/release.json` 首项指定，构建核对 APK 文件名、大小和 SHA-256，不再按文件名排序猜最新 APK。APK 清单仍是上游来源，更新渠道限制见 [迁移指南](MIGRATION.md#更新机制的边界)。

`build-info.json` 同时放在 ZIP 内和 Release 附件中，记录完整源码提交、dirty 标记、源码树摘要、Python/zlib 版本、关键依赖来源/版本/输入及解压后哈希、面板文件摘要和包内文件校验和。`SHA256SUMS` 记录其他四项发布资产的哈希，避免对 ZIP 自身摘要造成循环引用。它验证完整性，不是数字签名。同一源码、固定输入和同一工具链重建应一致；跨 Python/zlib 版本不能保证字节完全相同，记录工具链后再复核。

有未提交修改的本地包会明确记录 `dirty=true`，可以审查、验证，发布工具会拒绝它。源码快照创建后如果再改其输入文件，构建也会拒绝，须重新导出；不能将它伪装成已提交的正式包。正式标签构建将记录最终的新提交。

## 触发条件与正式发布

| 操作 | 新工作流的结果 |
| --- | --- |
| 仅本地编辑或提交 | 不触发远程工作流 |
| 推送 `main`，包括修改根 `Surfing.json` | 只触发 Alpha：校验、构建、上传 30 天有效的 Actions artifact；同分支新运行可取消尚未完成的旧运行 |
| 推送名称匹配 `v*-astra.*` 的标签 | 触发 Release：校验标签和版本、构建、保存 Actions artifact、创建/续传草稿、验证附件后**自动公开稳定版并设为 latest** |
| 其他分支推送、单独更新 `data` | 不触发上述两条工作流 |
| 重跑既有 Release 运行 | 同一源码/资产可恢复草稿或确认已发布；不会覆盖公开版本、回退 latest 或移动标签 |

标签必须已经存在且解析到构建的完整提交。工作流不创建或移动标签；发布使用 `--verify-tag`。不要误把“推送一个版本标签”当成仅建立标记，这会授权工作流公开发布。GitHub `GITHUB_TOKEN` 产生的推送通常不会递归触发工作流；正式标签应在批准后通过用户授权的 Git 凭据推送，并确认确实出现了 Release 运行。

首次发布分为独立确认：

1. 确认提交本次审查过的文件；再确认推送 `origin main`（此时只产生 Alpha）。
2. 下载新 Alpha 做必要的 Android 实机检查，或明确接受尚未完成的设备验证范围。检查覆盖安装、配置选择、核心能力、订阅、账号权限和实际流量；发布工具不会代替维护者判断这些结果。
3. 确认在最终审查提交创建稳定标签，例如 `v7.8.4-astra.1`；确认推送该标签及其自动公开发布后果。推送前核对远端 `main`、标签目标、版本号和待合入上游状态，不重用或强移标签。
4. 等工作流结束，读取公开的 latest 清单，核对它的 ZIP/日志链接与资产哈希，再按迁移指南手动覆盖安装。若 GitHub 缓存暂未刷新，稍后重新核对，不改用上游清单。

### 失败与重试

- 构建、下载或校验失败：不执行发布步骤。旧稳定版继续可用；首版仍无稳定入口。已推送标签不被移动或删除，修复若需改源码，应使用新的版本名、递增代码号和新标签。
- 部分附件上传失败：Release 留在 draft，更新清单不会对设备公开，旧 latest 不变。重跑相同标签构建，已有草稿附件逐个核对，匹配则跳过，缺失则补传，全部验证后再公开。
- 已有附件与重建结果不同：停止，保持原附件，不自动 `--clobber` 或清理。检查源码、依赖和工具链；可使用此前保留的已验证 Actions bundle，在匹配的源码/工具链下经批准恢复发布，或者发布新版本。
- 已经公开：相同资产重跑成功返回且不作修改；不同资产拒绝。修复采用新版本，不替换旧包，旧清单缓存仍能下载对应资产。
- 版本落后、同代码号、未知格式的现有稳定 Release 或目标标签被改变：拒绝发布。稳定工作流串行，并在上传前后检查代码号，避免旧运行覆盖较新稳定版。

发布辅助脚本 `python tools/publish_release.py <已验证目录>` **会写 GitHub**，仅在得到发布授权后使用；普通本地测试不会调用真实 GitHub 写操作。它先完整验证本地 bundle，再校验远端标签和版本；最后一次 API 修改才把完整草稿公开，且只允许发布到 AstraSolis/Surfing。

## 统计、清理与上游合并

下载徽章直接读取 Fork 的 GitHub Releases 统计，不再读取带有上游基数的 `data/stats.json`。Alpha 工作流移除 `Fetch-Data` 依赖和定时统计，不读写 data 分支；保留远端既有 data 内容，统计故障不影响构建和发布。

`cleanup.yml` 未修改；2026-11-06 只读检查显示它仍为 `disabled_fork`。不要因本次迁移启用或手动运行；其手动触发保留数量为零，会删除历史运行。新流程没有删除旧 Alpha 附件或历史 Release 的步骤。Actions artifact 的 30 天正常到期与该历史清理工作流不同。

本次基于 `320a690` 的个人功能继续开发；已获取到上游 `ed10889`（SurfingTile v7.1.0）和 `1ac1513`（按应用断网），按当前决定暂缓合并。今后重点复核 `module.prop`、根清单、`build.sh`、两条工作流、安装器与配置；新的运行文件必须出现在源码清单和 ZIP，升级部署仍由安装器单独负责。图标、规则源、上游说明、GPL 许可证、第三方核心/面板/二进制和 APK 来源不批量改成 Fork URL。
