#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
STATE_PATH = APP_DIR / "mode.json"
SINGBOX_CONFIG = Path("/etc/sing-box/architoken-xray-tun.json")
SINGBOX_SERVICE = "architoken-xray-tun.service"
XRAY_SERVICE = "xray-client"
RULE_SET_SOURCE = Path("/tmp/architoken-sing-box/rule-set")
RULE_SET_DIR = Path("/etc/sing-box/rule-set")
CACHE_DIR = Path("/var/cache/architoken-vpn")

XRAY_SOCKS = 10808
XRAY_HTTP = 10809
PORTS = {
    "mixed": 51867,
    "socks": 51869,
    "http": 51871,
    "api": 51873,
}
TUN_NAME = "architoken"
VPS_IPS = ["203.0.113.10", "198.51.100.20"]
VALID_MODES = ("privacy", "proxy", "tun")
MODE_LABELS = {
    "privacy": "全局代理（TUN 接管，公网全走 Xray）",
    "proxy": "系统代理（高级兜底，仅命令行）",
    "tun": "国内直连（TUN 接管，国内直连 / 国外代理）",
}


def run(cmd, timeout=30, check=False, env=None):
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "命令执行失败"
        raise RuntimeError(f"{' '.join(cmd)}: {detail}")
    return proc


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


def gsettings(args):
    return run(["gsettings", *args], timeout=5, env=desktop_env())


def set_system_proxy(enabled):
    if enabled:
        commands = [
            ["set", "org.gnome.system.proxy", "mode", "manual"],
            ["set", "org.gnome.system.proxy", "use-same-proxy", "false"],
            ["set", "org.gnome.system.proxy", "autoconfig-url", ""],
            [
                "set",
                "org.gnome.system.proxy",
                "ignore-hosts",
                "['localhost','127.0.0.0/8','::1','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','100.64.0.0/10','*.local']",
            ],
            ["set", "org.gnome.system.proxy.http", "enabled", "true"],
            ["set", "org.gnome.system.proxy.http", "host", "127.0.0.1"],
            ["set", "org.gnome.system.proxy.http", "port", str(XRAY_HTTP)],
            ["set", "org.gnome.system.proxy.https", "host", "127.0.0.1"],
            ["set", "org.gnome.system.proxy.https", "port", str(XRAY_HTTP)],
            ["set", "org.gnome.system.proxy.socks", "host", "127.0.0.1"],
            ["set", "org.gnome.system.proxy.socks", "port", str(XRAY_SOCKS)],
        ]
    else:
        commands = [["set", "org.gnome.system.proxy", "mode", "none"]]
    for command in commands:
        result = gsettings(command)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def read_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(mode):
    state = {
        "mode": mode,
        "label": MODE_LABELS[mode],
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "xray_socks": XRAY_SOCKS,
        "xray_http": XRAY_HTTP,
        "tun_interface": TUN_NAME,
        "tun_ports": PORTS,
    }
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def service_active(name):
    result = run(["systemctl", "is-active", name], timeout=5)
    if result.returncode != 0 and "Failed to connect to bus" in result.stderr:
        return None
    return result.stdout.strip() == "active"


def service_enabled(name):
    result = run(["systemctl", "is-enabled", name], timeout=5)
    if result.returncode != 0 and "Failed to connect to bus" in result.stderr:
        return None
    return result.stdout.strip() == "enabled"


def port_open(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            return sock.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return None


def ensure_rule_sets():
    RULE_SET_DIR.mkdir(parents=True, exist_ok=True)
    required = ["geosite-cn.srs", "geosite-geolocation-!cn.srs", "geoip-cn.srs"]
    for name in required:
        dst = RULE_SET_DIR / name
        src = RULE_SET_SOURCE / name
        if src.exists():
            shutil.copy2(src, dst)
        if not dst.exists():
            raise RuntimeError(f"缺少 sing-box 规则集: {dst}")


def base_dns(mode):
    servers = [
        {"type": "fakeip", "tag": "fakeip", "inet4_range": "198.18.0.0/15"},
        {
            "type": "https",
            "tag": "cn-ali",
            "server": "223.5.5.5",
            "tls": {"server_name": "dns.alidns.com"},
        },
        {
            "type": "https",
            "tag": "cn-dnspod",
            "server": "1.12.12.12",
            "tls": {"server_name": "doh.pub"},
        },
        {
            "type": "https",
            "tag": "foreign-cloudflare",
            "server": "1.1.1.1",
            "detour": "xray-socks",
            "tls": {"server_name": "cloudflare-dns.com"},
        },
        {
            "type": "https",
            "tag": "foreign-google",
            "server": "8.8.8.8",
            "detour": "xray-socks",
            "tls": {"server_name": "dns.google"},
        },
    ]
    rules = []
    if mode == "tun":
        rules.extend(
            [
                {"domain_suffix": ["cn"], "action": "route", "server": "cn-ali"},
                {"rule_set": "geosite-cn", "action": "route", "server": "cn-ali"},
                {
                    "rule_set": "geosite-geolocation-!cn",
                    "action": "route",
                    "server": "foreign-cloudflare",
                },
            ]
        )
    rules.append({"query_type": ["A", "AAAA"], "action": "route", "server": "fakeip"})
    return {
        "servers": servers,
        "rules": rules,
        "final": "foreign-cloudflare",
        "strategy": "ipv4_only",
        "disable_cache": False,
    }


def build_config(mode):
    route_exclude = [
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        *[f"{ip}/32" for ip in VPS_IPS],
    ]
    tun_inbound = {
        "type": "tun",
        "tag": "tun-in",
        "interface_name": TUN_NAME,
        "address": ["172.19.0.1/30"],
        "mtu": 9000,
        "auto_route": True,
        "strict_route": True,
        "stack": "gvisor",
        "route_exclude_address": route_exclude,
        "platform": {
            "http_proxy": {
                "enabled": False,
                "server": "127.0.0.1",
                "server_port": PORTS["mixed"],
            }
        },
    }
    if mode == "tun":
        tun_inbound["route_exclude_address_set"] = ["geoip-cn"]

    route_rules = [
        {"port": 53, "action": "hijack-dns"},
        {"ip_cidr": [f"{ip}/32" for ip in VPS_IPS], "action": "route", "outbound": "direct"},
        {"action": "sniff", "sniffer": ["tls", "http"], "timeout": "300ms"},
        {"ip_is_private": True, "action": "route", "outbound": "direct"},
        {"port": 4369, "action": "route", "outbound": "block"},
    ]
    if mode == "tun":
        route_rules.extend(
            [
                {"domain_suffix": ["cn"], "action": "route", "outbound": "direct"},
                {"rule_set": "geosite-cn", "action": "route", "outbound": "direct"},
                {"rule_set": "geoip-cn", "action": "route", "outbound": "direct"},
            ]
        )
    route_rules.append(
        {"rule_set": "geosite-geolocation-!cn", "action": "route", "outbound": "xray-socks"}
    )

    return {
        "log": {"level": "warn", "timestamp": True},
        "dns": base_dns(mode),
        "inbounds": [
            tun_inbound,
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": PORTS["mixed"],
            },
            {
                "type": "socks",
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "listen_port": PORTS["socks"],
            },
            {
                "type": "http",
                "tag": "http-in",
                "listen": "127.0.0.1",
                "listen_port": PORTS["http"],
            },
        ],
        "outbounds": [
            {
                "type": "socks",
                "tag": "xray-socks",
                "server": "127.0.0.1",
                "server_port": XRAY_SOCKS,
                "version": "5",
            },
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "auto_detect_interface": True,
            "default_domain_resolver": "cn-ali",
            "rules": route_rules,
            "rule_set": [
                {
                    "type": "local",
                    "tag": "geosite-cn",
                    "format": "binary",
                    "path": str(RULE_SET_DIR / "geosite-cn.srs"),
                },
                {
                    "type": "local",
                    "tag": "geosite-geolocation-!cn",
                    "format": "binary",
                    "path": str(RULE_SET_DIR / "geosite-geolocation-!cn.srs"),
                },
                {
                    "type": "local",
                    "tag": "geoip-cn",
                    "format": "binary",
                    "path": str(RULE_SET_DIR / "geoip-cn.srs"),
                },
            ],
            "final": "xray-socks",
        },
        "experimental": {
            "cache_file": {
                "enabled": True,
                "path": str(CACHE_DIR / "sing-box-cache.db"),
                "store_rdrc": True,
            },
            "clash_api": {"external_controller": f"127.0.0.1:{PORTS['api']}"},
        },
    }


def root_apply(mode):
    if mode not in VALID_MODES:
        raise SystemExit(f"未知模式: {mode}")
    if mode == "proxy":
        run(["systemctl", "disable", "--now", SINGBOX_SERVICE], timeout=30)
        return

    ensure_rule_sets()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SINGBOX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    config = build_config(mode)

    fd, tmp_path = tempfile.mkstemp(
        prefix=".architoken-xray-tun.", suffix=".json", dir=str(SINGBOX_CONFIG.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        run(["sing-box", "check", "-c", tmp_path], timeout=30, check=True)
        if SINGBOX_CONFIG.exists():
            backup = SINGBOX_CONFIG.with_suffix(
                f".json.bak-{time.strftime('%Y%m%d-%H%M%S')}"
            )
            shutil.copy2(SINGBOX_CONFIG, backup)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, SINGBOX_CONFIG)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    run(["systemctl", "daemon-reload"], timeout=20, check=True)
    run(["systemctl", "enable", SINGBOX_SERVICE], timeout=20, check=True)
    run(["systemctl", "restart", SINGBOX_SERVICE], timeout=30, check=True)


def call_root(mode):
    if os.geteuid() == 0:
        root_apply(mode)
        return
    cmd = ["pkexec", sys.executable, str(Path(__file__).resolve()), "--root", mode]
    result = run(cmd, timeout=90)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "授权或服务切换失败"
        raise RuntimeError(detail)


def apply_mode(mode):
    if mode not in VALID_MODES:
        raise SystemExit(f"usage: vpn-mode [{'|'.join(VALID_MODES)}]")
    call_root(mode)
    if mode == "proxy":
        set_system_proxy(True)
    else:
        set_system_proxy(False)
    write_state(mode)
    print(f"ArchIToken-VPN 已切换为: {MODE_LABELS[mode]}")


def current_status():
    state = read_state()
    mode = state.get("mode") if state.get("mode") in VALID_MODES else ""
    tun_active = service_active(SINGBOX_SERVICE)
    if not mode:
        mode = "tun" if tun_active else "proxy"
    proxy_mode = gsettings(["get", "org.gnome.system.proxy", "mode"]).stdout.strip().strip("'")
    return {
        "mode": mode,
        "label": MODE_LABELS.get(mode, mode),
        "xray_active": service_active(XRAY_SERVICE),
        "xray_enabled": service_enabled(XRAY_SERVICE),
        "tun_active": tun_active,
        "tun_enabled": service_enabled(SINGBOX_SERVICE),
        "tun_interface": TUN_NAME,
        "tun_interface_exists": Path(f"/sys/class/net/{TUN_NAME}").exists(),
        "system_proxy": proxy_mode or "unknown",
        "xray_ports": {
            "socks": XRAY_SOCKS,
            "http": XRAY_HTTP,
            "socks_open": port_open(XRAY_SOCKS),
            "http_open": port_open(XRAY_HTTP),
        },
        "tun_ports": {**PORTS, **{f"{k}_open": port_open(v) for k, v in PORTS.items()}},
        "updated_at": state.get("updated_at", ""),
    }


def print_status(as_json):
    status = current_status()
    if as_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return
    print(f"当前模式: {status['label']}")
    print(f"Xray: {'active' if status['xray_active'] else 'inactive'} · 10808/10809")
    print(
        f"TUN: {'active' if status['tun_active'] else 'inactive'} · "
        f"{status['tun_interface']} · mixed {PORTS['mixed']} / socks {PORTS['socks']} / http {PORTS['http']}"
    )
    print(f"系统代理: {status['system_proxy']}")


def main():
    parser = argparse.ArgumentParser(description="ArchIToken-VPN mode controller")
    parser.add_argument("mode", nargs="?", choices=VALID_MODES + ("status",))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", choices=VALID_MODES)
    args = parser.parse_args()

    try:
        if args.root:
            if os.geteuid() != 0:
                raise SystemExit("--root 只能由 root/pkexec 调用")
            root_apply(args.root)
        elif args.mode == "status" or not args.mode:
            print_status(args.json)
        else:
            apply_mode(args.mode)
    except Exception as exc:
        print(f"ArchIToken-VPN 模式切换失败: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
