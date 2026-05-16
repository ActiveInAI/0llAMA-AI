# Security Policy

This repository must stay free of production VPN secrets.

Before publishing changes, scan for:

- `vless://`, `vmess://`, `trojan://`, `ss://`
- UUID-like values
- `pbk=`, `sid=`, Reality private/public keys
- subscription URLs and 3x-ui panel paths
- personal emails and API tokens

Use `examples/nodes.example.json` for public examples and keep real node data in local/private deployment storage.
