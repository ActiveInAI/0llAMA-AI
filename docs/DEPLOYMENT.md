# 部署流程

本文档描述 ArchIToken-VPN 的生产部署步骤。公开仓库只提供工具与模板，不包含真实生产凭证。

## 1. VPS 侧

### 1.1 基础加固

1. 使用最小化 Linux 发行版。
2. 禁用密码 SSH 登录，使用密钥登录。
3. 配置防火墙，只开放必要端口。
4. 安装系统更新。
5. 配置时间同步。
6. 准备日志轮转和备份目录。

### 1.2 安装 Xray-core

推荐以 Xray-core 为服务端和本机主代理引擎。当前项目文档锁定参考版本：

- Xray-core `v26.3.27`
- 上游发布页：<https://github.com/XTLS/Xray-core/releases/tag/v26.3.27>

生产部署时可以升级到更高版本，但升级前必须在备用节点验证：

```bash
xray run -test -c /etc/xray/config.json
systemctl restart xray
systemctl status xray --no-pager
```

### 1.3 配置 VLESS Reality

服务端入站建议保持：

- 协议：VLESS
- 传输：TCP
- 安全层：Reality
- flow：`xtls-rprx-vision`
- fingerprint：`chrome`
- 入站端口：生产端口先不在公开仓库固定，按 VPS 配置执行

生产配置必须保存在私有环境，不提交到公开仓库。

### 1.4 验证

从客户端验证：

```bash
curl -fsS --socks5-hostname 127.0.0.1:10808 https://api.ipify.org
curl -fsS --proxy http://127.0.0.1:10809 https://www.google.com/generate_204
```

## 2. Linux 客户端 / 运维端

### 2.1 安装用户态文件

```bash
git clone https://github.com/ActiveInAI/ArchIToken-VPN.git
cd ArchIToken-VPN
./install.sh
```

### 2.2 准备 Xray 本机配置

把私有 Xray 配置放在：

```text
/etc/xray-client/config.json
```

要求：

- 保留本机 SOCKS `10808`
- 保留本机 HTTP `10809`
- 自动入口使用 `socks-auto`、`http-auto`
- 节点出站使用 `proxy-{city}` 或 `proxy-{node-code}`

### 2.3 启动服务

```bash
systemctl status xray-client --no-pager
systemctl restart xray-client
vpn-status
```

## 3. TUN / 路由层

TUN 层用于接管系统流量。生产环境可以使用 sing-box 作为外围 TUN 路由层，但主代理仍是 Xray。

建议：

- TUN 接口名：`architoken`
- 国内直连：国内 IP/域名直连
- 国外代理：转发到 Xray `10808/10809`
- DNS：DoH 或可信 DNS，上游配置由生产环境决定
- strict route：开启，降低多网卡和 DNS 泄漏风险

注意：

- TUN 需要 root 权限或 systemd 服务。
- 不要改动 Xray 本机 `10808/10809`。
- 不要在未验证时切换生产 Reality 入站端口。

## 4. 新增节点

节点代码规则：

```text
国家 ISO-3166 alpha-3 + IATA 城市代码 + A序号
```

示例：

- `USA-LAX-A1`
- `NLD-AMS-A1`
- `SGP-SIN-A1`
- `JPN-NRT-A1`

托盘新增节点流程：

1. 打开托盘。
2. 点击“新增节点并导出 HTML”。
3. 填写节点代码、城市、IP、端口、服务商、面板 URL、订阅 URL。
4. 粘贴完整 VLESS Reality 链接。
5. 选择是否写入本机 Xray。
6. 选择本地 HTML 模板。
7. 生成新版 HTML 文档。
8. 可选：接入成功后立即切换到新节点。

## 5. Windows / Android 用户分发

### Windows

推荐兼容 v2rayN：

- 版本参考：`v2rayN 7.21.3`
- 发布页：<https://github.com/2dust/v2rayN/releases/tag/7.21.3>
- 支持 VLESS 分享链接、订阅、二维码导入。
- v2rayN 7.21.3 发布说明包含 Windows Xray TUN 支持。

### Android

推荐兼容 v2rayNG：

- 版本参考：`v2rayNG 2.1.7`
- 发布页：<https://github.com/2dust/v2rayNG/releases>
- 支持本地 SOCKS、动态端口、基于进程包名的路由、Xray TUN 场景下的可选出站别名。

## 6. 发布前检查

每次公开发布前运行：

```bash
./scripts/scan-secrets.sh
```

确认没有生产凭证后再提交。
