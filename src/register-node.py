#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

CONFIG_PATH = os.environ.get("XRAY_CONFIG_PATH", "/etc/xray-client/config.json")


def valid_ip(text):
    parts = text.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def node_tag(code):
    return f"proxy-{code.lower()}"


def inbound_tag(prefix, code):
    return f"{prefix}-{code.lower()}"


def parse_vless(link):
    parsed = urlparse(link.strip())
    if parsed.scheme != "vless":
        raise ValueError("VLESS 链接必须以 vless:// 开头")
    user_id = unquote(parsed.username or "")
    if not user_id:
        raise ValueError("VLESS 链接缺少 UUID")
    host = parsed.hostname or ""
    port = parsed.port or 443
    query = {key: values[-1] for key, values in parse_qs(parsed.query, keep_blank_values=True).items()}
    if not host:
        raise ValueError("VLESS 链接缺少服务端地址")
    return {
        "id": user_id,
        "address": host,
        "port": int(port),
        "network": query.get("type", "tcp") or "tcp",
        "security": query.get("security", "reality") or "reality",
        "encryption": query.get("encryption", "none") or "none",
        "flow": query.get("flow", ""),
        "fingerprint": query.get("fp", "chrome") or "chrome",
        "serverName": query.get("sni", ""),
        "publicKey": query.get("pbk", ""),
        "shortId": query.get("sid", ""),
        "spiderX": query.get("spx", "/") or "/",
    }


def make_outbound(tag, parsed):
    reality = {
        "show": False,
        "fingerprint": parsed["fingerprint"],
        "serverName": parsed["serverName"],
        "publicKey": parsed["publicKey"],
        "shortId": parsed["shortId"],
        "spiderX": parsed["spiderX"],
    }
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": parsed["address"],
                    "port": parsed["port"],
                    "users": [
                        {
                            "id": parsed["id"],
                            "encryption": parsed["encryption"],
                            "flow": parsed["flow"],
                        }
                    ],
                }
            ]
        },
        "streamSettings": {
            "network": parsed["network"],
            "security": parsed["security"],
            "realitySettings": reality,
        },
    }


def make_inbound(tag, port, protocol):
    inbound = {
        "tag": tag,
        "listen": "127.0.0.1",
        "port": int(port),
        "protocol": protocol,
        "settings": {},
    }
    if protocol == "socks":
        inbound["settings"] = {"auth": "noauth", "udp": True}
    return inbound


def insert_before_system_outbounds(outbounds, item):
    system_tags = {"direct", "block"}
    for index, outbound in enumerate(outbounds):
        if outbound.get("tag") in system_tags:
            outbounds.insert(index, item)
            return
    outbounds.append(item)


def replace_rule(rules, inbound_tags, outbound):
    inbound_tags = list(inbound_tags)
    tag_set = set(inbound_tags)
    for rule in rules:
        if set(rule.get("inboundTag") or []) == tag_set:
            rule["outboundTag"] = outbound
            return
    rules.insert(
        1,
        {
            "type": "field",
            "inboundTag": inbound_tags,
            "outboundTag": outbound,
        },
    )


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: register-node.py <node-payload.json>")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    code = (payload.get("node_code") or "").upper()
    if not re.match(r"^[A-Z]{3}-[A-Z0-9]{3}-A[0-9]+$", code):
        raise SystemExit("节点代码格式错误，应为 USA-LAX-A1")
    ip = payload.get("ip") or ""
    if ip and not valid_ip(ip):
        raise SystemExit("公网 IP 格式错误")
    parsed = parse_vless(payload.get("vless") or "")
    tag = payload.get("outbound") or node_tag(code)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    outbounds = config.setdefault("outbounds", [])
    outbounds[:] = [outbound for outbound in outbounds if outbound.get("tag") != tag]
    insert_before_system_outbounds(outbounds, make_outbound(tag, parsed))

    dedicated_tags = []
    inbounds = config.setdefault("inbounds", [])
    socks_port = payload.get("socks")
    http_port = payload.get("http")
    if socks_port:
        socks_tag = inbound_tag("socks", code)
        inbounds[:] = [item for item in inbounds if item.get("tag") != socks_tag]
        inbounds.append(make_inbound(socks_tag, socks_port, "socks"))
        dedicated_tags.append(socks_tag)
    if http_port:
        http_tag = inbound_tag("http", code)
        inbounds[:] = [item for item in inbounds if item.get("tag") != http_tag]
        inbounds.append(make_inbound(http_tag, http_port, "http"))
        dedicated_tags.append(http_tag)
    if dedicated_tags:
        replace_rule(config.setdefault("routing", {}).setdefault("rules", []), dedicated_tags, tag)

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

    test = subprocess.run(["/usr/local/bin/xray", "run", "-test", "-c", CONFIG_PATH], capture_output=True, text=True, timeout=20)
    if test.returncode != 0:
        shutil.copy2(backup, CONFIG_PATH)
        detail = test.stderr.strip() or test.stdout.strip() or "Xray 配置校验失败"
        raise SystemExit(f"已回滚配置：{detail}")

    if CONFIG_PATH == "/etc/xray-client/config.json":
        subprocess.run(["systemctl", "restart", "xray-client"], check=True)
    print(f"registered node: {code} -> {tag}")


if __name__ == "__main__":
    main()
