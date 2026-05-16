# Third Party Notices

ArchIToken-VPN integrates with or documents workflows for upstream proxy projects. This repository does not vendor their source code.

## Xray-core

- Repository: <https://github.com/XTLS/Xray-core>
- Referenced release: <https://github.com/XTLS/Xray-core/releases/tag/v26.3.27>
- License: Mozilla Public License 2.0
- Role: main proxy engine and server/client runtime target.

If ArchIToken-VPN distributes Xray binaries, keep the upstream license notice and provide access to the corresponding Xray source as required by MPL-2.0. Modifications to Xray-covered source files must remain under MPL-2.0.

## v2rayN

- Repository: <https://github.com/2dust/v2rayN>
- Referenced release: <https://github.com/2dust/v2rayN/releases/tag/7.21.3>
- License: GNU General Public License v3.0
- Role: Windows client compatibility reference for VLESS links, subscriptions, QR import, Xray TUN and user workflows.

Do not copy or modify v2rayN code in this MIT-licensed repository unless the resulting distribution is handled under GPL-3.0-compatible terms.

## v2rayNG

- Repository: <https://github.com/2dust/v2rayNG>
- Referenced release page: <https://github.com/2dust/v2rayNG/releases>
- Referenced release: 2.1.7
- License: GNU General Public License v3.0
- Role: Android client compatibility reference for VLESS links, subscriptions, QR import, process routing, Xray TUN and user workflows.

Do not copy or modify v2rayNG code in this MIT-licensed repository unless the resulting distribution is handled under GPL-3.0-compatible terms.

## Practical Rule

- Protocol compatibility, link generation, subscription generation, QR code generation and documentation are acceptable in this repository.
- Directly copying GPL client code requires the derivative client to follow GPL-3.0.
- Production node credentials must remain outside this public repository.
