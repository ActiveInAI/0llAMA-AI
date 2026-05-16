#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

PATTERN='vless://[0-9a-fA-F]{8}-|vmess://[A-Za-z0-9+/=]{20,}|trojan://[^[:space:]<]+|(^|[^A-Za-z])ss://[^[:space:]<]+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|(?i)(privateKey|private_key|password|passwd|token|secret|webhook)[[:space:]]*[:=][[:space:]]*["'\'']?[^"'\''][[:space:]<>{}]+|pbk=[^&[:space:]<>{}]+|sid=[0-9a-fA-F]{2,}|ActiveInAI@gmail|93\.179\.112\.188|185\.239\.69\.219|nv9lbwry|ketrv5'

if rg -n --hidden --glob '!.git/**' --glob '!THIRD_PARTY_NOTICES.md' --glob '!README.md' --glob '!SECURITY.md' --glob '!scripts/scan-secrets.sh' "$PATTERN" "$ROOT"; then
  echo "Potential secret-like content found. Review before publishing." >&2
  exit 1
fi

echo "No obvious production secrets found."
