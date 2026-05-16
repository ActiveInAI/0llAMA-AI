#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CONFIG_PATH = os.environ.get("XRAY_CONFIG_PATH", "/etc/xray-client/config.json")
APP_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = APP_DIR / "nodes.json"
BUILTIN_NODE_TO_OUTBOUND = {
    "USA-LAX-A1": "proxy-la",
    "NLD-AMS-A1": "proxy-ams",
}
BUILTIN_DEDICATED = {
    "USA-LAX-A1": {"socks-la", "http-la"},
    "NLD-AMS-A1": {"socks-ams", "http-ams"},
}


def node_tag(code):
    return f"proxy-{code.lower()}"


def load_registry_nodes():
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    nodes = {}
    for code, node in (data.get("nodes") or {}).items():
        code = code.upper()
        nodes[code] = dict(node or {})
    return nodes


def build_maps():
    registry = load_registry_nodes()
    node_to_outbound = dict(BUILTIN_NODE_TO_OUTBOUND)
    dedicated = {code: set(tags) for code, tags in BUILTIN_DEDICATED.items()}
    for code, node in registry.items():
        outbound = node.get("outbound") or node_tag(code)
        node_to_outbound[code] = outbound
        tags = set()
        if node.get("socks"):
            tags.add(f"socks-{code.lower()}")
        if node.get("http"):
            tags.add(f"http-{code.lower()}")
        if tags:
            dedicated[code] = tags
    return node_to_outbound, dedicated


def inbound_tags(rule):
    return set(rule.get("inboundTag") or [])


def main():
    node_to_outbound, dedicated = build_maps()
    if len(sys.argv) != 2 or sys.argv[1] not in node_to_outbound:
        valid = ", ".join(sorted(node_to_outbound))
        raise SystemExit(f"usage: switch-node.py <{valid}>")

    selected = node_to_outbound[sys.argv[1]]
    proxy_outbounds = set(node_to_outbound.values())
    dedicated_by_tag = {}
    for code, tags in dedicated.items():
        for tag in tags:
            dedicated_by_tag[tag] = node_to_outbound[code]

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    for rule in config.get("routing", {}).get("rules", []):
        tags = inbound_tags(rule)
        dedicated_target = next((dedicated_by_tag[tag] for tag in tags if tag in dedicated_by_tag), "")
        if dedicated_target:
            rule["outboundTag"] = dedicated_target
        elif {"socks-auto", "http-auto"} & tags:
            rule["outboundTag"] = selected
        elif rule.get("outboundTag") in proxy_outbounds:
            rule["outboundTag"] = selected

    st = os.stat(CONFIG_PATH)
    backup = f"{CONFIG_PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(CONFIG_PATH, backup)

    config_dir = os.path.dirname(CONFIG_PATH)
    fd, tmp_path = tempfile.mkstemp(prefix=".config.", suffix=".json", dir=config_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.chown(tmp_path, st.st_uid, st.st_gid)
        os.chmod(tmp_path, st.st_mode & 0o777)
        os.replace(tmp_path, CONFIG_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if CONFIG_PATH == "/etc/xray-client/config.json":
        subprocess.run(["systemctl", "restart", "xray-client"], check=True)
    print(f"active node: {sys.argv[1]}")


if __name__ == "__main__":
    main()
