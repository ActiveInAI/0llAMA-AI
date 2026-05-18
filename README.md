# ArchIToken-VPN

ArchIToken-VPN 是围绕 **Xray VLESS / TCP / Reality** 构建的团队 VPN 运维与全平台接入工具。项目目标不是替换 Xray，而是在 Xray 主代理引擎外面补齐桌面托盘、节点切换、TUN 路由、诊断、WebRTC 检测、文档模板和未来全平台客户端接入流程。

本仓库是公开仓库，所有生产凭证均已脱敏。不要把真实 VLESS 链接、UUID、Reality key、ShortID、订阅 token、3x-ui 面板路径、个人邮箱或生产节点 IP 提交到这里。

## 项目边界

- 主代理引擎：保留 Xray，不把核心代理逻辑改成其他引擎。
- 本机入口：保留 Xray SOCKS/HTTP `10808/10809`，避免破坏 Zed/Codex、浏览器、终端和其他依赖。
- TUN 层：作为外围路由接管层，用于“全局代理”和“国内直连 / 国外代理”两种用户可见模式。
- 节点命名：使用 `国家 ISO-3166 alpha-3` + `IATA 城市代码` + `A序号`，例如 `USA-LAX-A1`、`NLD-AMS-A1`、`SGP-SIN-A1`。
- 运维文档：公开仓库只放安全模板；真实节点资料在本机或私有密钥管理系统中维护。

## 仓库结构

```text
.
├── bin/                         # vpn-mode / vpn-status 用户命令包装器
├── desktop/                     # Linux 桌面托盘启动文件
├── docs/                        # 部署、架构、客户端策略和脱敏 HTML 文档
├── examples/                    # nodes/mode 示例，全部为占位符
├── scripts/                     # 发布前安全扫描工具
├── src/                         # 托盘、诊断、节点切换、节点注册、TUN 模式脚本
├── web/                         # 本地 WebRTC 泄漏检测页
├── install.sh                   # 当前用户安装脚本
├── LICENSE                      # ArchIToken-VPN 项目许可
├── SECURITY.md                  # 安全策略
└── THIRD_PARTY_NOTICES.md       # Xray / v2rayN / v2rayNG 第三方声明
```

## 当前能力

- Linux 托盘控制台：中文 UI、红黄绿状态灯、当前节点、出口 IP、TUN 状态、系统代理状态。
- 两种模式：`全局代理` 和 `国内直连`。
- 节点切换：内置节点和后续新增节点均可从托盘切换。
- 新增节点：托盘可填写节点信息、导入 VLESS Reality 链接、写入 Xray 出站、生成 HTML 文档。
- 诊断：`vpn-status` 输出 Xray、端口、TUN、出口、DNS、Cloudflare、指纹、连通性、WebRTC 检测入口。
- 文档：管理员版、全平台用户版、运维管理文档均为脱敏模板。

## 全平台客户端路线

ArchIToken-VPN 可以借鉴和兼容 Xray、v2rayN、v2rayNG，但必须分清“协议兼容”和“代码复用”：

- **独立客户端仓库**：全平台客户端作为关联项目单独开发，仓库为 [ActiveInAI/ArchIToken-VPN-Client](https://github.com/ActiveInAI/ArchIToken-VPN-Client)，采用 GPL-3.0-or-later。
- **Linux / 运维端**：本仓库维护托盘、诊断、TUN、节点注册和模板导出。
- **Windows**：优先兼容 v2rayN 的 VLESS 分享链接、订阅导入、Xray TUN 使用方式；若直接 fork/修改 v2rayN 代码，需要遵守 GPL-3.0。
- **Android**：优先兼容 v2rayNG 的 VLESS 分享链接、订阅、二维码、Xray TUN/路由能力；若直接 fork/修改 v2rayNG 代码，需要遵守 GPL-3.0。
- **macOS / iOS**：先支持通用 VLESS Reality 分享链接、二维码和订阅，再评估原生客户端。
- **Web 管理端**：只做节点模板、订阅生成、BOM 式运维清单和审计，不在公开端存储生产凭证。

详细说明见 [docs/CLIENT_STRATEGY.md](docs/CLIENT_STRATEGY.md)。

## 快速安装

### 全平台客户端

ArchIToken-VPN Client 已作为独立 GPL 项目发布：

- Release 页面：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/latest>
- v0.5.1：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/tag/v0.5.1>
- Windows x64：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-windows-x86_64.exe>
- Windows arm64：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-windows-arm64.exe>
- Linux x64：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-linux-x86_64>
- Linux arm64：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-linux-arm64>
- macOS x64：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-macos-x86_64>
- macOS arm64：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-macos-arm64>
- Android debug APK：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-android-universal-debug.apk>
- Android unsigned release APK：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-android-universal-release-unsigned.apk>
- Android unsigned release AAB：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-android-universal-release-unsigned.aab>
- iOS simulator：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-ios-simulator.zip>
- iOS Xcode source：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/ArchIToken-VPN-Client-ios-source.zip>
- Python wheel：<https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/download/v0.5.1/architoken_vpn_client-0.5.1-py3-none-any.whl>

说明：Windows、Linux、macOS 已覆盖 x64 与 arm64。Android 已接入 `VpnService`、Xray 配置生成、私有 `xray + tun2socks` 或单体 `runner` 运行器注入、运行时缺失保护，并在 CI 中预留 Android keystore 签名入口；未配置私有签名材料时只发布 debug APK、未签名 release APK 和未签名 AAB。iOS 已接入嵌入式 PacketTunnel extension、`PacketRuntime` / `PacketRunner` 私有内核挂钩、NetworkExtension 配置管理和签名导出脚本；未配置 Apple 证书、描述文件和私有 PacketCore 时只发布 simulator 构建和 Xcode 源码包。`v0.5.1` 已使用新版 GitHub Actions 重新打包，并固定 Windows x64 构建到 `windows-2025-vs2026`。生产运行器、证书、keystore、描述文件必须通过 GitHub Actions secrets 或私有包注入，不提交到公开仓库。

### 运维端工具

```bash
./install.sh
```

安装脚本会把用户态文件安装到：

- `~/.local/share/architoken-vpn`
- `~/.local/bin/vpn-mode`
- `~/.local/bin/vpn-status`
- `~/.local/share/applications/architoken-vpn-tray.desktop`
- `~/.config/autostart/architoken-vpn-tray.desktop`

系统级服务不会由公开包自动安装，因为它们依赖私有生产配置：

- `/etc/xray-client/config.json`
- `/etc/sing-box/architoken-xray-tun.json`
- systemd 服务、路由规则、防火墙策略、私有节点密钥

完整部署流程见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 发布前安全检查

```bash
./scripts/scan-secrets.sh
```

扫描会拦截常见生产泄漏：

- 真实 VLESS/VMess/Trojan/SS 链接
- UUID
- Reality `pbk` / `sid` / private key
- 订阅 token、面板路径、个人邮箱
- 明确列入禁止公开的生产 IP 或密钥片段

## 许可证

- ArchIToken-VPN 本仓库代码默认采用 MIT License。
- Xray-core 使用 MPL-2.0。
- v2rayN 使用 GPL-3.0。
- v2rayNG 使用 GPL-3.0。

如果只是兼容分享链接、订阅格式、二维码和配置导入流程，通常属于协议/数据格式互操作；如果复制、fork 或修改 v2rayN/v2rayNG 代码并分发，衍生作品需要遵守 GPL-3.0 的源码公开和同许可证分发要求。

第三方项目版本与许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
