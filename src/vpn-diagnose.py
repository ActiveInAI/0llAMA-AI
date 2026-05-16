#!/usr/bin/env python3
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
import textwrap
import unicodedata
from pathlib import Path

CONFIG_PATH = "/etc/xray-client/config.json"
AUTO_SOCKS = 10808
AUTO_HTTP = 10809
APP_DIR = Path(__file__).resolve().parent
MODE_SCRIPT = APP_DIR / "vpn-mode.py"
WEBRTC_CHECK = APP_DIR / "webrtc-check.html"
WEBRTC_URL = "http://127.0.0.1:18765/webrtc-check.html"
TUN_SERVICE = "architoken-xray-tun.service"
TUN_INTERFACE = "architoken"
TUN_PORTS = {"mixed": 51867, "socks": 51869, "http": 51871, "api": 51873}
REGISTRY_PATH = APP_DIR / "nodes.json"

NODES = {
    "USA-LAX-A1": {
        "label": "美国 洛杉矶",
        "country": "US",
        "ip": "203.0.113.10",
        "outbound": "proxy-la",
    },
    "NLD-AMS-A1": {
        "label": "荷兰 阿姆斯特丹",
        "country": "NL",
        "ip": "198.51.100.20",
        "outbound": "proxy-ams",
    },
}


def node_outbound_tag(code, node):
    return node.get("outbound") or f"proxy-{code.lower()}"


def load_nodes():
    nodes = {code: dict(node) for code, node in NODES.items()}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    for code, node in (data.get("nodes") or {}).items():
        code = code.upper()
        item = dict(node or {})
        item.setdefault("country", code.split("-", 1)[0])
        item["outbound"] = node_outbound_tag(code, item)
        nodes[code] = item
    return nodes


NODES = load_nodes()
OUTBOUND_TO_NODE = {v["outbound"]: k for k, v in NODES.items()}
IP_TO_NODE = {v["ip"]: k for k, v in NODES.items() if v.get("ip")}


def run(cmd, timeout=10, env=None):
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except Exception as e:
        return "", str(e), 124


def desktop_env():
    env = os.environ.copy()
    uid = os.getuid()
    runtime = f"/run/user/{uid}"
    if os.path.exists("/run/user/1000/bus"):
        runtime = "/run/user/1000"
    elif not os.path.exists(runtime) and os.path.exists("/run/user/1000"):
        runtime = "/run/user/1000"
    env.setdefault("XDG_RUNTIME_DIR", runtime)
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
    env.setdefault("DISPLAY", ":1")
    return env


def clean_env():
    env = os.environ.copy()
    for key in [
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ]:
        env.pop(key, None)
    return env


def curl(url, proxy=True, timeout=12, extra=None):
    cmd = ["curl", "-fsS", "-4", "--max-time", str(timeout)]
    if proxy:
        cmd += ["--socks5-hostname", f"127.0.0.1:{AUTO_SOCKS}"]
    if extra:
        cmd += extra
    cmd.append(url)
    out, _, rc = run(cmd, timeout=timeout + 3, env=clean_env())
    return out if rc == 0 else ""


def curl_json(url, proxy=True, timeout=12):
    out = curl(url, proxy=proxy, timeout=timeout)
    if not out:
        return {}
    try:
        return json.loads(out)
    except Exception:
        return {"_raw": out[:500]}


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def active_outbound(cfg):
    for rule in cfg.get("routing", {}).get("rules", []):
        inbound = set(rule.get("inboundTag") or [])
        if {"socks-auto", "http-auto"} & inbound:
            return rule.get("outboundTag") or ""
    return ""


def outbound_settings(cfg, outbound):
    for item in cfg.get("outbounds", []):
        if item.get("tag") == outbound:
            user = (((item.get("settings") or {}).get("vnext") or [{}])[0].get("users") or [{}])[0]
            reality = (item.get("streamSettings") or {}).get("realitySettings") or {}
            return {
                "network": (item.get("streamSettings") or {}).get("network", ""),
                "security": (item.get("streamSettings") or {}).get("security", ""),
                "encryption": user.get("encryption", ""),
                "flow": user.get("flow", ""),
                "fingerprint": reality.get("fingerprint", ""),
                "serverName": reality.get("serverName", ""),
                "shortId": reality.get("shortId", ""),
            }
    return {}


def gsetting(schema_key):
    parts = schema_key.split()
    out, _, _ = run(["gsettings", "get", *parts], timeout=4, env=desktop_env())
    return out.strip().strip("'")


def service_status(name="xray-client"):
    out, _, _ = run(["systemctl", "is-active", name], timeout=4)
    return out or "unknown"


def port_listening(port):
    out, _, _ = run(["ss", "-tln"], timeout=4)
    return f":{port} " in out or f":{port}\n" in out


def mode_status():
    if MODE_SCRIPT.exists():
        out, _, rc = run(["/usr/bin/python3", str(MODE_SCRIPT), "status", "--json"], timeout=8)
        if rc == 0 and out:
            try:
                return json.loads(out)
            except Exception:
                pass
    tun_active = service_status(TUN_SERVICE) == "active"
    return {
        "mode": "tun" if tun_active else "proxy",
        "label": "国内直连（TUN 推断）" if tun_active else "系统代理（高级兜底，推断）",
        "tun_active": tun_active,
        "tun_enabled": False,
        "tun_interface": TUN_INTERFACE,
        "tun_interface_exists": Path(f"/sys/class/net/{TUN_INTERFACE}").exists(),
        "system_proxy": gsetting("org.gnome.system.proxy mode"),
        "tun_ports": TUN_PORTS,
    }


def parse_trace(text):
    result = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def ptr(ip):
    out, _, rc = run(["dig", "+short", "-x", ip], timeout=6)
    if rc == 0 and out:
        return ", ".join(x.rstrip(".") for x in out.splitlines()[:3])
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def whois_brief(ip):
    out, _, rc = run(["whois", ip], timeout=10)
    if rc != 0 or not out:
        return {}
    keys = [
        "CIDR",
        "NetRange",
        "inetnum",
        "route",
        "origin",
        "originAS",
        "OrgName",
        "org-name",
        "netname",
        "descr",
        "country",
    ]
    data = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        if k in keys and k not in data:
            data[k] = re.sub(r"\s+", " ", v).strip()
    return data


def speed_probe():
    cmd = [
        "curl",
        "-o",
        "/dev/null",
        "-sS",
        "-4",
        "--max-time",
        "18",
        "--socks5-hostname",
        f"127.0.0.1:{AUTO_SOCKS}",
        "-w",
        "code=%{http_code} connect=%{time_connect} ttfb=%{time_starttransfer} total=%{time_total} speed=%{speed_download}",
        "https://speed.cloudflare.com/__down?bytes=1000000",
    ]
    out, _, rc = run(cmd, timeout=22, env=clean_env())
    if rc != 0 or not out:
        return "失败"
    m = re.search(r"speed=([0-9.]+)", out)
    if not m:
        return out
    bps = float(m.group(1)) * 8
    mbps = bps / 1_000_000
    return f"{mbps:.2f} Mbps · {out}"


def site_probe(url):
    cmd = [
        "curl",
        "-o",
        "/dev/null",
        "-sS",
        "-4",
        "--max-time",
        "10",
        "--socks5-hostname",
        f"127.0.0.1:{AUTO_SOCKS}",
        "-w",
        "%{http_code} connect=%{time_connect}s ttfb=%{time_starttransfer}s total=%{time_total}s",
        url,
    ]
    out, _, rc = run(cmd, timeout=13, env=clean_env())
    if rc != 0 or not out:
        return "失败"
    code = out.split()[0] if out else ""
    if "chatgpt.com" in url and code == "403":
        return f"{out} · curl 被站点防护拦截，浏览器登录态需另测"
    return out


def risk_score(ipapi, node_country, reported_country):
    score = 10
    notes = []
    if ipapi.get("hosting") is True:
        score += 35
        notes.append("hosting=true")
    if ipapi.get("proxy") is True:
        score += 35
        notes.append("proxy=true")
    if ipapi.get("mobile") is True:
        score += 10
        notes.append("mobile=true")
    if node_country and reported_country and node_country != reported_country:
        score += 15
        notes.append("节点国家与检测国家不一致")
    return min(score, 100), ", ".join(notes) if notes else "未见明显代理/机房标记"


def text_width(text):
    width = 0
    for ch in str(text):
        width += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return width


def pad(text, width):
    return str(text) + " " * max(0, width - text_width(text))


def section(title):
    print()
    print(f"  {title}")
    print("  " + "─" * 72)


def line(label, value):
    value = str(value if value not in (None, "") else "未知")
    prefix = f"  {pad(label, 14)}  "
    continuation = " " * text_width(prefix)
    chunks = textwrap.wrap(
        value,
        width=88,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
    ) or ["未知"]
    print(prefix + chunks[0])
    for chunk in chunks[1:]:
        print(continuation + chunk)


def site_line(host, value):
    line(host, value)


def main():
    cfg = load_config()
    mode = mode_status()
    out = active_outbound(cfg)
    node_code = OUTBOUND_TO_NODE.get(out, "UNKNOWN")
    node = NODES.get(node_code, {})

    direct_ip = curl("https://api.ipify.org", proxy=False, timeout=10)
    ipify = curl_json("https://api.ipify.org?format=json", proxy=True, timeout=10)
    ipinfo = curl_json("https://ipinfo.io/json", proxy=True, timeout=12)
    ipapi = curl_json(
        "http://ip-api.com/json/?fields=status,message,country,countryCode,regionName,city,lat,lon,timezone,isp,org,as,asname,query,reverse,proxy,hosting,mobile",
        proxy=True,
        timeout=12,
    )
    ifconfig = curl_json("https://ifconfig.co/json", proxy=True, timeout=12)
    trace = parse_trace(curl("https://1.1.1.1/cdn-cgi/trace", proxy=True, timeout=10))
    dns_google = curl_json(
        "https://dns.google/resolve?name=o-o.myaddr.l.google.com&type=TXT",
        proxy=True,
        timeout=10,
    )
    cn_route_probe = curl("https://myip.ipip.net", proxy=False, timeout=10)

    proxy_ip = (
        ipify.get("ip")
        or ipinfo.get("ip")
        or ipapi.get("query")
        or ifconfig.get("ip")
        or trace.get("ip")
    )
    measured_node = IP_TO_NODE.get(proxy_ip, "UNKNOWN")
    if measured_node != "UNKNOWN":
        node_code = measured_node
        node = NODES[node_code]

    whois_data = whois_brief(proxy_ip) if proxy_ip else {}
    ptr_name = ptr(proxy_ip) if proxy_ip else ""
    settings = outbound_settings(cfg, node.get("outbound", out))
    ip_decimal = ""
    if proxy_ip:
        try:
            ip_decimal = int(ipaddress.ip_address(proxy_ip))
        except Exception:
            pass

    country = ipapi.get("countryCode") or ipinfo.get("country") or ifconfig.get("country_iso")
    city = ipapi.get("city") or ipinfo.get("city") or ifconfig.get("city")
    region = ipapi.get("regionName") or ipinfo.get("region") or ifconfig.get("region_name")
    lat = ipapi.get("lat") or ifconfig.get("latitude")
    lon = ipapi.get("lon") or ifconfig.get("longitude")
    score, risk_notes = risk_score(ipapi, node.get("country"), country)

    dns_answers = []
    for ans in dns_google.get("Answer", []) if isinstance(dns_google, dict) else []:
        data = ans.get("data", "")
        if data:
            dns_answers.append(data.strip('"'))
    ip_range = (
        whois_data.get("CIDR")
        or whois_data.get("route")
        or whois_data.get("inetnum")
        or (dns_answers[0] if dns_answers else "")
    )

    print("══════════════════════════════════════")
    print("     ArchIToken-VPN · 详细诊断")
    print("══════════════════════════════════════")
    section("服务")
    line("当前模式", mode.get("label"))
    line("Xray 主引擎", service_status("xray-client"))
    line("TUN 路由层", f"{service_status(TUN_SERVICE)} · {TUN_INTERFACE}={'存在' if mode.get('tun_interface_exists') else '不存在'}")
    line("SOCKS5 10808", "监听" if port_listening(AUTO_SOCKS) else "未监听")
    line("HTTP 10809", "监听" if port_listening(AUTO_HTTP) else "未监听")
    line("TUN 本地端口", f"mixed {TUN_PORTS['mixed']} · socks {TUN_PORTS['socks']} · http {TUN_PORTS['http']} · api {TUN_PORTS['api']}")
    line("系统代理", mode.get("system_proxy") or gsetting("org.gnome.system.proxy mode"))
    line("终端代理", "已设置" if os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY") else "未设置")

    section("节点")
    line("当前节点", f"{node_code} · {node.get('label', '未知')}")
    line("Xray 自动路由", f"10808/10809 -> {node_code}")
    line("系统出口", direct_ip or "失败（不代表 VPS 故障）")
    line("VPN 出口", proxy_ip or "失败")
    line("国内直连检测", cn_route_probe or "失败")
    line("出口一致性", "一致" if len({x for x in [ipify.get('ip'), ipinfo.get('ip'), ipapi.get('query'), ifconfig.get('ip'), trace.get('ip')] if x}) == 1 else "多源不一致")
    if mode.get("mode") == "tun":
        line("路由策略", "国内域名/IP 直连，国外流量经 Xray；国内网站会看到本机真实出口")
    elif mode.get("mode") == "privacy":
        line("路由策略", "公网流量默认经 Xray，仅本地网段和 VPS 直连")
    elif mode.get("mode") == "proxy":
        line("路由策略", "关闭 TUN，仅支持系统/应用显式代理")

    section("IP 情报")
    line("IP 来源", f"ipify={ipify.get('ip')} · ipinfo={ipinfo.get('ip')} · ip-api={ipapi.get('query')} · ifconfig={ifconfig.get('ip')} · cloudflare={trace.get('ip')}")
    line("国家/城市", f"{country} · {region} · {city}")
    line("IP 位置", f"{lat},{lon} · timezone={ipapi.get('timezone') or ipinfo.get('timezone') or ifconfig.get('time_zone')}")
    line("IP 定位", f"ipinfo={ipinfo.get('city')}/{ipinfo.get('region')}/{ipinfo.get('country')} · ip-api={ipapi.get('city')}/{ipapi.get('regionName')}/{ipapi.get('countryCode')} · ifconfig={ifconfig.get('city')}/{ifconfig.get('region_name')}/{ifconfig.get('country_iso')}")
    line("IP 数字", ip_decimal)
    line("IP 范围", ip_range)
    line("反向 DNS", ptr_name or ipapi.get("reverse"))

    section("归属与风险")
    line("ASN", ipapi.get("as") or ipinfo.get("org"))
    line("企业", ipapi.get("asname") or whois_data.get("netname"))
    line("服务商", ipapi.get("isp") or ipinfo.get("org"))
    line("所有者", whois_data.get("OrgName") or whois_data.get("org-name") or whois_data.get("netname") or whois_data.get("descr"))
    line("IP 风险", f"{score}/100 · {risk_notes}")
    line("原生 IP", "否/数据中心出口" if ipapi.get("hosting") or ipapi.get("proxy") else "可能是原生住宅/运营商出口")
    line("IP 出口", f"Xray {AUTO_SOCKS}/{AUTO_HTTP} · {node_code} · {mode.get('mode')}")

    section("DNS 与指纹")
    line("DNS", "; ".join(dns_answers[:3]) or "未返回")
    line("Cloudflare", f"colo={trace.get('colo')} loc={trace.get('loc')} tls={trace.get('tls')} kex={trace.get('kex')} http={trace.get('http')}")
    line("指纹信息", f"Reality={settings.get('security')} · fp={settings.get('fingerprint')} · sni={settings.get('serverName')} · encryption={settings.get('encryption')} · flow={settings.get('flow') or 'none'}")

    section("连通性")
    for url in ["https://www.google.com", "https://chatgpt.com", "https://github.com"]:
        site_line(url.replace("https://", ""), site_probe(url))
    line("网速", speed_probe())

    chromium_desktop = Path("/home/insome/.local/share/applications/org.chromium.Chromium.desktop")
    chromium_flags = chromium_desktop.read_text(encoding="utf-8", errors="ignore") if chromium_desktop.exists() else ""
    webrtc_policy = "disable_non_proxied_udp" if "disable_non_proxied_udp" in chromium_flags else "未发现 Chromium 防泄漏启动参数"
    section("浏览器")
    line("WebRTC", f"{webrtc_policy} · 浏览器实测页: {WEBRTC_URL}")
    print()


if __name__ == "__main__":
    main()
