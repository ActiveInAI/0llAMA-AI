# ArchIToken-VPN 架构

## 分层

```text
用户应用
  ├─ 浏览器 / Zed / Codex / Git / ChatGPT 桌面端
  └─ 不支持显式代理的软件
        │
        ▼
本机接入层
  ├─ Xray SOCKS 10808
  ├─ Xray HTTP 10809
  └─ TUN 接口 architoken
        │
        ▼
路由层
  ├─ 全局代理：公网流量统一走 Xray
  └─ 国内直连：国内 IP/域名直连，国外流量走 Xray
        │
        ▼
Xray 出站
  ├─ proxy-la  -> USA-LAX-A1
  ├─ proxy-ams -> NLD-AMS-A1
  └─ proxy-{node-code} -> 动态新增节点
        │
        ▼
VPS 入站
  └─ Xray VLESS / TCP / Reality / Vision
```

## 核心原则

- Xray 是主代理引擎，托盘和 TUN 只是外围控制层。
- `10808/10809` 是稳定本机入口，不随模式切换改变。
- TUN 模式只负责系统流量接管、DNS 捕获、国内直连和国外代理分流。
- 生产 Reality 入站端口由 VPS 配置决定，公开仓库不保存真实参数。
- 动态节点通过 `nodes.json` 和 Xray routing/outbound 更新接入。

## 关键文件

- `src/tray.py`：桌面入口，负责状态展示、模式切换、节点切换、新增节点、文档导出。
- `src/vpn-mode.py`：模式控制，负责系统代理、TUN 服务和模式状态。
- `src/vpn-diagnose.py`：诊断输出，负责连通性、出口、DNS、指纹、WebRTC 检查。
- `src/switch-node.py`：修改 Xray routing，让自动入口切到目标节点。
- `src/register-node.py`：解析 VLESS Reality 链接，写入 Xray outbound/routing，先校验后重启。
- `web/webrtc-check.html`：本地 WebRTC ICE candidate 检测页。

## 模式

### 全局代理

用于出差、漫游、临时网络不可信或需要确保所有公网流量走代理的场景。

- TUN 接管公网流量。
- 国内站点也可能走代理。
- 流量消耗更高，但出口一致性更强。

### 国内直连

日常推荐模式。

- TUN 接管系统流量。
- 国内 IP/域名直连。
- 国外流量走 Xray。
- 更省流量，国内访问更快。

## 节点注册

新增节点必须提供完整 VLESS Reality 链接。IP 本身不足以构造 Xray 出站，因为还需要：

- UUID
- Reality public key
- ShortID
- SNI
- flow
- encryption
- transport/security 参数

注册流程：

1. 托盘填写节点代码、城市、IP、端口和 VLESS 链接。
2. `register-node.py` 解析链接并生成 Xray outbound。
3. 写入临时配置。
4. 执行 `xray run -test`。
5. 校验通过后替换配置并重启 Xray。
6. 写入 `nodes.json`，托盘刷新后可直接切换。

## 不进入公开仓库的内容

- `/etc/xray-client/config.json`
- Reality private key / public key
- 真实 VLESS 链接
- 订阅 URL 和 token
- 3x-ui 面板路径
- 生产 VPS IP 和面板地址
- 用户邮箱、成员账号、审计日志
