# 全平台客户端策略

ArchIToken-VPN 的全平台路线分为两层：协议兼容优先，代码复用谨慎。

独立客户端仓库：

- Repository: <https://github.com/ActiveInAI/ArchIToken-VPN-Client>
- License: GPL-3.0-or-later
- Scope: Windows / Linux / macOS / Android / iOS simulator 客户端构建
- Relationship: 本仓库继续负责运维、部署、Linux 托盘和服务端文档；客户端仓库负责面向用户的全平台软件。
- Latest release: <https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/latest>
- Current release: <https://github.com/ActiveInAI/ArchIToken-VPN-Client/releases/tag/v0.3.0>

## 可以直接借鉴的内容

- VLESS / Reality 分享链接格式。
- 订阅 URL 内容格式。
- QR 二维码导入流程。
- 节点分组、别名、延迟测试、出口检测逻辑。
- TUN 模式下的路由分流思路。
- Windows / Android 用户操作流程。

这些属于配置、交互流程和协议互操作，不要求复制上游客户端代码。

## 需要谨慎的内容

v2rayN 和 v2rayNG 都是 GPL-3.0 项目。如果直接复制、fork、修改并分发它们的代码，ArchIToken 的衍生客户端必须遵守 GPL-3.0，包括提供对应源码和保留许可证声明。

更稳妥的路线：

1. 本仓库维护 ArchIToken-VPN 的配置、节点、订阅、二维码、诊断和运维能力。
2. Windows 用户先使用 v2rayN 官方客户端导入 ArchIToken 订阅。
3. Android 用户先使用 v2rayNG 官方客户端导入 ArchIToken 订阅。
4. 如果后续需要自研客户端，优先写独立 UI 和配置生成器，通过 Xray-core 或系统服务调用实现，不直接复制 GPL 客户端代码。
5. 如果决定 fork v2rayN/v2rayNG，则建立单独仓库并按 GPL-3.0 发布完整源码。

## 平台计划

`v0.3.0` 已在客户端仓库 CI 中覆盖：

- Windows x64 / arm64
- Linux x64 / arm64
- macOS x64 / arm64
- Android universal debug APK
- Android unsigned release APK
- Android unsigned release AAB
- iOS unsigned simulator app
- iOS Xcode source package

未完成的发布级事项：Windows 代码签名、macOS notarization、Android keystore 签名、iOS 真机/TestFlight/App Store 签名。

### Linux

当前仓库已经实现：

- 托盘 UI
- 模式切换
- 节点切换
- 节点注册
- 诊断输出
- WebRTC 检测
- HTML 文档导出

后续可补：

- systemd 服务安装器
- TUN 配置生成器
- 图形化日志查看器
- 订阅生成器

### Windows

第一阶段：

- 生成 v2rayN 可导入的 VLESS 分享链接。
- 生成订阅 URL。
- 生成 QR 码。
- 编写 Windows 用户版说明。

第二阶段：

- 开发 ArchIToken-VPN Windows 配置助手。
- 检测 v2rayN 安装路径。
- 一键导入订阅。
- 调用 v2rayN 或 Xray-core 进行延迟和出口检查。

### Android

已完成：

- 中文界面。
- VLESS Reality 分享链接解析。
- 订阅 URL 拉取与 base64/plain 订阅解码。
- 剪贴板导入和复制。
- 节点详情展示。
- Xray outbound JSON 生成。
- CI 输出 debug APK、未签名 release APK、未签名 release AAB。

后续发布级事项：

- 接入正式 Android keystore。
- 生成已签名 APK/AAB。
- 按目标渠道补齐 Play Console 或企业分发流程。

### macOS / iOS

已完成：

- iOS SwiftUI 中文界面。
- VLESS Reality 分享链接解析。
- 订阅 URL 拉取与 base64/plain 订阅解码。
- 剪贴板导入和复制。
- 节点详情展示。
- Xray outbound JSON 生成。
- CI 输出 iOS simulator 构建和 Xcode 源码包。

后续发布级事项：

- 接入 Apple Developer Team ID。
- 配置 bundle id、证书、描述文件、签名身份。
- 建立 TestFlight / App Store Connect 发布流水线。

## 统一数据模型

每个节点至少包含：

```json
{
  "code": "USA-LAX-A1",
  "label": "美国 洛杉矶",
  "country": "US",
  "city": "LAX",
  "ip": "203.0.113.10",
  "remote_port": 443,
  "outbound": "proxy-usa-lax-a1",
  "provider": "provider-name",
  "panel": "https://203.0.113.10:2053/{PANEL_PATH}/panel/",
  "subscription": "https://203.0.113.10:2096/sub/{SUBSCRIPTION_TOKEN}",
  "enabled": true
}
```

公开示例必须使用占位符或文档保留 IP，不使用生产 IP。
