# ArchIToken-VPN

ArchIToken-VPN is a desktop operations toolkit around Xray VLESS / TCP / Reality and an outer TUN routing layer.

This public package intentionally ships with sanitized example nodes and placeholder credentials. Do not commit production VLESS URLs, UUIDs, Reality keys, subscription tokens, 3x-ui panel paths, or personal emails to a public repository.

## Included

- `src/tray.py`: GTK/Ayatana tray UI with Chinese status labels, traffic-light state, two visible modes, node switching, node registration, and HTML document export.
- `src/vpn-mode.py`: Xray-preserving mode controller for global proxy and China-direct TUN routing.
- `src/vpn-diagnose.py`: detailed status and connectivity diagnostics.
- `src/switch-node.py`: Xray routing switcher for built-in and dynamically registered nodes.
- `src/register-node.py`: VLESS/Reality node registration helper with Xray config validation and rollback.
- `web/webrtc-check.html`: local WebRTC leak check page.
- `docs/*.safe.html`: redacted operations and user documentation templates.
- `examples/nodes.example.json`: IATA-style node code examples such as `USA-LAX-A1` and `NLD-AMS-A1`.

## Install For Current User

```bash
./install.sh
```

The installer copies files into `~/.local/share/architoken-vpn`, installs `vpn-mode` and `vpn-status` wrappers under `~/.local/bin`, and enables the tray desktop entry for autostart.

System services for Xray and the TUN layer are not installed by this public package because those depend on your private `/etc/xray-client/config.json`, sing-box config, route-set files, and host firewall policy.

## Node Codes

Use ISO-3166 alpha-3 country code + IATA city code + sequence:

- `USA-LAX-A1`: United States, Los Angeles, first node
- `NLD-AMS-A1`: Netherlands, Amsterdam, first node
- `SGP-SIN-A1`: Singapore, Singapore, first node

## Security Rules

- Keep Xray as the main proxy engine.
- Do not change local Xray SOCKS/HTTP `10808/10809` unless the dependent tools are updated together.
- Do not publish production Reality inbound ports, VLESS links, UUIDs, public keys, ShortIDs, subscription paths, or panel paths.
- Register new nodes through the tray or `register-node.py`; the helper validates Xray config before restarting the service.
