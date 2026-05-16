#!/usr/bin/env python3
# ArchIToken-VPN · 桌面托盘指示器
# 依赖: python3-gi, gir1.2-ayatanaappindicator3-0.1

import gi, os, signal, subprocess, threading, time, urllib.request, socket, json, warnings, html, re, tempfile
import http.server
from datetime import datetime
from pathlib import Path
warnings.filterwarnings("ignore", category=DeprecationWarning)
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, GLib, Gdk, GdkPixbuf, AyatanaAppIndicator3 as AppIndicator

def re_match_ip(text):
    parts = text.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False

NODES = {
    "USA-LAX-A1": {
        "label": "美国 洛杉矶",
        "ip": "203.0.113.10",
        "socks": 10828,
        "http": 10829,
        "panel": "https://203.0.113.10:2053/{PANEL_PATH}/panel/",
        "enabled": True,
        "note": "主节点 · 续费后继续承载主流量",
    },
    "NLD-AMS-A1": {
        "label": "荷兰 阿姆斯特丹",
        "ip": "198.51.100.20",
        "socks": 10818,
        "http": 10819,
        "panel": "https://198.51.100.20:2053/{PANEL_PATH}/panel/",
        "enabled": True,
        "note": "备用节点 · 当前可用",
    },
}
DEFAULT_NODE = "USA-LAX-A1"
AUTO_SOCKS_PORT = 10808
AUTO_HTTP_PORT = 10809
VPS_IPS = {node["ip"] for node in NODES.values()}
OUTBOUND_TO_NODE = {"proxy-la": "USA-LAX-A1", "proxy-ams": "NLD-AMS-A1"}
APP_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path.home() / "下载"
REGISTRY_PATH = APP_DIR / "nodes.json"
REGISTER_SCRIPT = str(APP_DIR / "register-node.py")
DEFAULT_TEMPLATE_PATHS = [
    DOWNLOAD_DIR / "ArchIToken-VPN-运维管理文档.html",
    DOWNLOAD_DIR / "ArchIToken-VPN-安全版双文档" / "ArchIToken-VPN-安全运维与隐私保护指南-管理员版.html",
    DOWNLOAD_DIR / "ArchIToken-VPN-安全版双文档" / "ArchIToken-VPN-团队安全接入指南-全平台用户版.html",
]
SWITCH_SCRIPT = str(APP_DIR / "switch-node.py")
DIAG_SCRIPT = str(APP_DIR / "vpn-diagnose.py")
MODE_SCRIPT = str(APP_DIR / "vpn-mode.py")
WEBRTC_CHECK = APP_DIR / "webrtc-check.html"
WEBRTC_HOST = "127.0.0.1"
WEBRTC_PORT = 18765
WEBRTC_URL = f"http://{WEBRTC_HOST}:{WEBRTC_PORT}/webrtc-check.html"
CHECK_INTERVAL = 30  # 秒
SCRIPT_PATH = str(Path(__file__).resolve())
MODE_LABELS = {
    "privacy": "全局代理",
    "tun": "国内直连",
    "proxy": "系统代理（高级兜底）",
}
BUILTIN_NODES = json.loads(json.dumps(NODES))
BUILTIN_OUTBOUNDS = {"USA-LAX-A1": "proxy-la", "NLD-AMS-A1": "proxy-ams"}


def node_outbound_tag(code, node=None):
    node = node or {}
    return node.get("outbound") or BUILTIN_OUTBOUNDS.get(code) or f"proxy-{code.lower()}"


def normalized_node(code, node):
    result = dict(node)
    result.setdefault("label", code)
    result.setdefault("ip", "")
    result.setdefault("enabled", True)
    result.setdefault("note", "")
    result["outbound"] = node_outbound_tag(code, result)
    for key in ("socks", "http", "remote_port"):
        value = result.get(key)
        if isinstance(value, str) and value.isdigit():
            result[key] = int(value)
    return result


def load_nodes():
    nodes = {code: normalized_node(code, node) for code, node in BUILTIN_NODES.items()}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    for code, node in (data.get("nodes") or {}).items():
        code = code.upper()
        if re.match(r"^[A-Z]{3}-[A-Z0-9]{3}-A[0-9]+$", code):
            nodes[code] = normalized_node(code, node)
    return nodes


def save_registry_node(code, node):
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"nodes": {}}
    data.setdefault("nodes", {})[code] = normalized_node(code, node)
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, REGISTRY_PATH)


def refresh_node_globals():
    global NODES, VPS_IPS, OUTBOUND_TO_NODE
    NODES = load_nodes()
    VPS_IPS = {node["ip"] for node in NODES.values() if node.get("ip")}
    OUTBOUND_TO_NODE = {node_outbound_tag(code, node): code for code, node in NODES.items()}


refresh_node_globals()


class WebRTCCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/webrtc-check.html"}:
            self.send_error(404)
            return
        try:
            body = WEBRTC_CHECK.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

class ArchITokenVPNTray:
    def __init__(self):
        self.indicator = AppIndicator.Indicator.new(
            "architoken-vpn",
            "network-vpn-symbolic",
            AppIndicator.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("ArchIToken-VPN")

        self.current_ip = "检测中..."
        self.service_active = False
        self.tun_active = False
        self.mode_status = {"mode": "tun", "label": MODE_LABELS["tun"]}
        self.active_node = DEFAULT_NODE
        self.webrtc_server = None
        self.dot_pixbufs = {}
        self.install_theme()
        self.ensure_webrtc_server()
        self.build_menu()
        
        # 启动后台状态检测
        threading.Thread(target=self.status_loop, daemon=True).start()
    
    def run_cmd(self, cmd, timeout=5):
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, 
                                    text=True, timeout=timeout)
            return result.stdout.strip(), result.returncode
        except Exception as e:
            return str(e), -1

    def install_theme(self):
        settings = Gtk.Settings.get_default()
        if settings:
            try:
                settings.set_property("gtk-menu-images", True)
            except Exception:
                pass
        css = b"""
        menu {
            background: #0b1220;
            color: #eef6ff;
            border: 1px solid #334155;
            font-family: "Noto Sans CJK SC", "Microsoft YaHei", "Inter", sans-serif;
        }
        menuitem {
            padding: 8px 15px;
            color: #eef6ff;
            font-family: "Noto Sans CJK SC", "Microsoft YaHei", "Inter", sans-serif;
        }
        menuitem:hover {
            background: #1d4ed8;
            color: #ffffff;
        }
        menuitem:disabled {
            color: #94a3b8;
        }
        separator {
            color: #334155;
        }
        textview, textview text {
            background: #0b1220;
            color: #eef2f8;
            font-family: "JetBrains Mono", "Noto Sans Mono CJK SC", monospace;
        }
        scrolledwindow {
            background: #0b1220;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def ensure_webrtc_server(self):
        if self.webrtc_server:
            return True
        try:
            server = http.server.ThreadingHTTPServer((WEBRTC_HOST, WEBRTC_PORT), WebRTCCheckHandler)
        except OSError:
            return True
        self.webrtc_server = server
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return True
    
    def check_service(self):
        out, _ = self.run_cmd("systemctl is-active xray-client")
        return out.strip() == "active"

    def check_tun_service(self):
        out, _ = self.run_cmd("systemctl is-active architoken-xray-tun.service")
        return out.strip() == "active"

    def get_mode_status(self):
        try:
            result = subprocess.run(
                ["/usr/bin/python3", MODE_SCRIPT, "status", "--json"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception:
            pass
        tun_active = self.check_tun_service()
        return {
            "mode": "tun" if tun_active else "proxy",
            "label": MODE_LABELS["tun"] if tun_active else MODE_LABELS["proxy"],
            "tun_active": tun_active,
            "system_proxy": self.read_gsetting("org.gnome.system.proxy mode"),
        }
    
    def check_port(self, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            r = s.connect_ex(('127.0.0.1', port))
            s.close()
            return r == 0
        except:
            return False

    def read_gsetting(self, schema_key):
        out, _ = self.run_cmd(f"gsettings get {schema_key}")
        return out.strip().strip("'")

    def get_active_node_code(self):
        try:
            with open("/etc/xray-client/config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            for rule in config.get("routing", {}).get("rules", []):
                inbound_tags = set(rule.get("inboundTag", []))
                if {"socks-auto", "http-auto"} & inbound_tags:
                    return OUTBOUND_TO_NODE.get(rule.get("outboundTag"), DEFAULT_NODE)
        except Exception:
            pass

        socks_port = self.read_gsetting("org.gnome.system.proxy.socks port")
        for code, node in NODES.items():
            if socks_port == str(node["socks"]):
                return code
        for code, node in NODES.items():
            if self.current_ip == node["ip"]:
                return code
        return DEFAULT_NODE

    def get_active_ports(self):
        return AUTO_SOCKS_PORT, AUTO_HTTP_PORT
    
    def get_proxy_ip(self):
        mode = self.mode_status.get("mode")
        if mode in {"privacy", "tun"} and self.tun_active:
            commands = [
                "curl -fsS --connect-timeout 3 --max-time 8 --noproxy '*' -4 https://api.ipify.org",
                "curl -fsS --connect-timeout 3 --max-time 8 --noproxy '*' -4 https://ifconfig.me",
                "curl -fsS --connect-timeout 3 --max-time 8 --noproxy '*' -4 https://1.1.1.1/cdn-cgi/trace | awk -F= '/^ip=/{print $2; exit}'",
            ]
        else:
            socks_port, _ = self.get_active_ports()
            commands = [
                f"curl -fsS --connect-timeout 3 --max-time 8 --socks5-hostname 127.0.0.1:{socks_port} -4 https://api.ipify.org",
                f"curl -fsS --connect-timeout 3 --max-time 8 --socks5-hostname 127.0.0.1:{socks_port} -4 https://ifconfig.me",
                f"curl -fsS --connect-timeout 3 --max-time 8 --socks5-hostname 127.0.0.1:{socks_port} -4 https://1.1.1.1/cdn-cgi/trace | awk -F= '/^ip=/{{print $2; exit}}'",
            ]
        for cmd in commands:
            out, rc = self.run_cmd(cmd, timeout=10)
            if rc == 0 and out and re_match_ip(out.strip()):
                return out.strip()
        return None
    
    def update_status(self):
        self.service_active = self.check_service()
        self.mode_status = self.get_mode_status()
        self.tun_active = bool(self.mode_status.get("tun_active"))
        self.active_node = self.get_active_node_code()
        socks_port, http_port = self.get_active_ports()
        socks_ok = self.check_port(socks_port)
        http_ok = self.check_port(http_port)
        
        if self.service_active and socks_ok:
            ip = self.get_proxy_ip()
            self.current_ip = ip if ip else "测试失败"
        else:
            self.current_ip = "服务未运行"
        
        # 更新图标状态
        if self.service_active and (self.current_ip in VPS_IPS or self.tun_active):
            self.indicator.set_icon_full("network-vpn-symbolic", "已连接")
            self.indicator.set_label(" 🟢", "")
        elif self.service_active:
            self.indicator.set_icon_full("network-vpn-acquiring-symbolic", "连接中")
            self.indicator.set_label(" 🟡", "")
        else:
            self.indicator.set_icon_full("network-vpn-disconnected-symbolic", "已断开")
            self.indicator.set_label(" 🔴", "")
        
        GLib.idle_add(self.rebuild_menu)
        return False
    
    def status_loop(self):
        while True:
            self.update_status()
            time.sleep(CHECK_INTERVAL)
    
    def build_menu(self):
        self.menu = Gtk.Menu()
        self.rebuild_menu()
        self.indicator.set_menu(self.menu)

    def append_item(self, label, callback=None, *args, sensitive=True, markup=False):
        item = Gtk.MenuItem()
        text = Gtk.Label()
        text.set_xalign(0)
        if markup:
            text.set_markup(label)
        else:
            text.set_text(label)
        item.add(text)
        item.set_sensitive(sensitive)
        if callback:
            item.connect('activate', callback, *args)
        self.menu.append(item)
        return item

    def append_status_item(self, level, label, callback=None, *args, sensitive=True, markup=False):
        item = Gtk.ImageMenuItem.new_with_label(label)
        dot = Gtk.Image.new_from_pixbuf(self.status_pixbuf(level))
        item.set_image(dot)
        item.set_always_show_image(True)
        item.set_sensitive(sensitive)
        if callback:
            item.connect('activate', callback, *args)
        self.menu.append(item)
        return item

    def status_color(self, level):
        return {
            "ok": (34, 197, 94),
            "warn": (250, 204, 21),
            "bad": (239, 68, 68),
        }.get(level, (250, 204, 21))

    def status_pixbuf(self, level):
        if level in self.dot_pixbufs:
            return self.dot_pixbufs[level]

        size = 14
        center = (size - 1) / 2
        radius = 5.4
        edge = 1.2
        red, green, blue = self.status_color(level)
        data = bytearray(size * size * 4)
        for y in range(size):
            for x in range(size):
                distance = ((x - center) ** 2 + (y - center) ** 2) ** 0.5
                offset = (y * size + x) * 4
                if distance <= radius:
                    alpha = 255
                elif distance <= radius + edge:
                    alpha = int(255 * (1 - (distance - radius) / edge))
                else:
                    alpha = 0
                data[offset] = red
                data[offset + 1] = green
                data[offset + 2] = blue
                data[offset + 3] = alpha

        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(bytes(data)),
            GdkPixbuf.Colorspace.RGB,
            True,
            8,
            size,
            size,
            size * 4,
        )
        self.dot_pixbufs[level] = pixbuf
        return pixbuf
    
    def rebuild_menu(self):
        refresh_node_globals()
        # 清空
        for child in self.menu.get_children():
            self.menu.remove(child)
        
        # 标题
        self.append_item('<b>ArchIToken-VPN 控制台</b>', markup=True)
        self.append_item('<span foreground="#93c5fd">主节点 USA-LAX-A1</span>  |  <span foreground="#c4b5fd">备用 NLD-AMS-A1</span>', markup=True)
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # 状态
        status_text = "正常运行" if self.service_active else "服务未运行"
        status_level = "ok" if self.service_active else "bad"
        self.append_status_item(status_level, f"连接状态：{status_text}")
        
        node = NODES.get(self.active_node, NODES[DEFAULT_NODE])
        node_text = f"当前节点：{self.active_node} · {node['label']}"
        node_level = "ok" if self.current_ip == node["ip"] else "warn"
        self.append_status_item(node_level, node_text)

        ip_text = f"出口 IP：{self.current_ip}"
        if self.current_ip in VPS_IPS:
            ip_text += " · 已通过"
            ip_level = "ok"
        elif self.current_ip in {"检测中...", "测试失败"}:
            ip_level = "warn"
        else:
            ip_level = "bad"
        self.append_status_item(ip_level, ip_text)

        mode_code = self.mode_status.get("mode", "proxy")
        mode_label = MODE_LABELS.get(mode_code, self.mode_status.get("label") or mode_code)
        mode_level = "ok" if mode_code in {"privacy", "tun"} and self.service_active else "warn"
        if not self.service_active:
            mode_level = "bad"
        self.append_status_item(mode_level, f"当前模式：{mode_label}")

        mode_out, _ = self.run_cmd("gsettings get org.gnome.system.proxy mode")
        manual_proxy = "manual" in mode_out
        tun_text = "已启用" if self.tun_active else "未启用"
        proxy_text = "开启（高级兜底）" if manual_proxy else "关闭"
        tun_level = "ok" if self.tun_active else ("warn" if mode_code == "proxy" else "bad")
        proxy_level = "warn" if manual_proxy else "ok"
        self.append_status_item(tun_level, f"TUN 路由层：{tun_text} · architoken")
        self.append_status_item(proxy_level, f"系统代理：{proxy_text}")
        
        self.menu.append(Gtk.SeparatorMenuItem())

        self.append_item('<span foreground="#94a3b8">模式切换</span>', markup=True)

        mode_descriptions = {
            "privacy": "TUN 接管全部公网流量，所有出口走 Xray",
            "tun": "TUN 接管系统流量，国内直连 / 国外代理，日常推荐",
        }
        for code in ("privacy", "tun"):
            selected = code == mode_code
            self.append_status_item(
                "ok" if selected else "warn",
                f"{MODE_LABELS[code]}：{mode_descriptions[code]}",
                self.select_mode,
                code,
            )

        self.menu.append(Gtk.SeparatorMenuItem())

        self.append_item('<span foreground="#94a3b8">节点选择（点击切换出口）</span>', markup=True)

        for code, node in NODES.items():
            selected = code == self.active_node
            role = "主节点" if code == DEFAULT_NODE else "备用"
            if not node.get("enabled", True):
                level = "bad"
                health = "暂停"
            elif selected and self.current_ip == node["ip"]:
                level = "ok"
                health = "当前出口"
            elif selected:
                level = "warn"
                health = "已选择，待检测"
            else:
                level = "warn"
                health = "可切换"
            self.append_status_item(
                level,
                f'{role}：{code} · {node["label"]} · {node["ip"]} · {health}',
                self.select_node,
                code,
            )
        
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # 操作菜单
        actions = [
            ("刷新状态", lambda w: threading.Thread(target=self.update_status, daemon=True).start()),
            ("详细连接测试", self.test_connection),
            ("打开 WebRTC 检测页", self.open_webrtc_check),
            ("重启 Xray / TUN 服务", self.restart_service),
            ("复制 SOCKS5 地址", self.copy_socks),
            ("新增节点并导出 HTML", self.export_node_html_dialog),
            ("打开配置文件", self.open_config),
            ("查看实时日志", self.open_log),
            ("打开当前节点 3x-ui 面板", self.open_panel),
        ]
        for label, cb in actions:
            item = Gtk.MenuItem(label=label)
            item.connect('activate', cb)
            self.menu.append(item)
        
        self.menu.append(Gtk.SeparatorMenuItem())
        
        quit_item = Gtk.MenuItem(label="退出托盘（代理服务继续运行）")
        quit_item.connect('activate', self.quit)
        self.menu.append(quit_item)
        
        self.menu.show_all()

    def select_mode(self, widget, code):
        label = MODE_LABELS.get(code, code)
        def do_switch():
            self.notify(f"正在切换 → {label}")
            result = subprocess.run(
                ["/usr/bin/python3", MODE_SCRIPT, code],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                msg = result.stderr.strip() or result.stdout.strip() or "模式切换失败"
                self.notify(msg[:180])
                GLib.idle_add(self.show_dialog, "ArchIToken-VPN · 模式切换失败", msg)
                return
            self.notify(f"已切换 → {label}")
            self.update_status()
        threading.Thread(target=do_switch, daemon=True).start()
        GLib.idle_add(self.rebuild_menu)
    
    def toggle_system_proxy(self, widget, is_on):
        if is_on:
            self.run_cmd("gsettings set org.gnome.system.proxy mode 'none'")
            self.notify("系统代理已关闭")
        else:
            node = NODES.get(self.active_node, NODES[DEFAULT_NODE])
            cmds = [
                "gsettings set org.gnome.system.proxy mode 'manual'",
                "gsettings set org.gnome.system.proxy use-same-proxy false",
                "gsettings set org.gnome.system.proxy autoconfig-url ''",
                "gsettings set org.gnome.system.proxy ignore-hosts ['localhost','127.0.0.0/8','::1','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','100.64.0.0/10','*.local']",
                "gsettings set org.gnome.system.proxy.http enabled true",
                "gsettings set org.gnome.system.proxy.http host '127.0.0.1'",
                f"gsettings set org.gnome.system.proxy.http port {AUTO_HTTP_PORT}",
                "gsettings set org.gnome.system.proxy.https host '127.0.0.1'",
                f"gsettings set org.gnome.system.proxy.https port {AUTO_HTTP_PORT}",
                "gsettings set org.gnome.system.proxy.socks host '127.0.0.1'",
                f"gsettings set org.gnome.system.proxy.socks port {AUTO_SOCKS_PORT}",
            ]
            for c in cmds: self.run_cmd(c)
            self.notify(f"系统代理已开启 → {self.active_node}")
        GLib.idle_add(self.rebuild_menu)

    def select_node(self, widget, code):
        self.active_node = code
        node = NODES[code]
        if not node.get("enabled", True):
            msg = (
                f"{code} · {node['ip']} 当前未启用，已暂停切换。\n\n"
                "请先在托盘脚本中恢复 enabled 状态，再重新切换。"
            )
            self.notify(f"{code} 当前未启用，未切换")
            GLib.idle_add(self.show_dialog, "ArchIToken-VPN · 节点未启用", msg)
            return
        def do_switch():
            self.notify(f"正在切换出口 → {code}")
            result = subprocess.run(
                ["pkexec", "/usr/bin/python3", SWITCH_SCRIPT, code],
                capture_output=True,
                text=True,
                timeout=45,
            )
            if result.returncode != 0:
                msg = result.stderr.strip() or result.stdout.strip() or "切换失败"
                self.notify(msg[:180])
                GLib.idle_add(self.show_dialog, "ArchIToken-VPN · 切换失败", msg)
                return
            self.notify(f"已切换出口 → {code} · {node['ip']}；系统代理未自动开启")
            self.update_status()
        threading.Thread(target=do_switch, daemon=True).start()
        GLib.idle_add(self.rebuild_menu)
    
    def test_connection(self, widget):
        def do_test():
            self.notify("正在执行详细连接测试...")
            result = subprocess.run(
                ["/usr/bin/python3", DIAG_SCRIPT],
                capture_output=True,
                text=True,
                timeout=90,
            )
            out = result.stdout.strip() or result.stderr.strip() or "测试失败"
            GLib.idle_add(self.show_dialog, "ArchIToken-VPN · 连接测试", out)
        threading.Thread(target=do_test, daemon=True).start()
    
    def show_dialog(self, title, msg):
        dialog = Gtk.Dialog(title=title, flags=Gtk.DialogFlags.MODAL)
        dialog.set_title(title)
        dialog.set_default_size(980, 720)
        dialog.set_resizable(True)
        dialog.add_button("关闭", Gtk.ResponseType.CLOSE)

        text = Gtk.TextView()
        text.set_editable(False)
        text.set_cursor_visible(False)
        text.set_monospace(True)
        text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text.get_buffer().set_text(msg)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(text)

        content = dialog.get_content_area()
        content.set_border_width(12)
        content.pack_start(scroll, True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def export_node_html_dialog(self, widget):
        dialog = Gtk.Dialog(title="ArchIToken-VPN · 新增节点导出", flags=Gtk.DialogFlags.MODAL)
        dialog.set_default_size(900, 800)
        dialog.set_resizable(True)
        dialog.add_button("取消", Gtk.ResponseType.CANCEL)
        dialog.add_button("导出 HTML", Gtk.ResponseType.OK)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(10)
        grid.set_margin_top(12)
        grid.set_margin_bottom(12)
        grid.set_margin_start(12)
        grid.set_margin_end(12)

        fields = [
            ("node_code", "节点代码", "USA-IAD-A1"),
            ("role", "节点角色", "新增节点"),
            ("label", "国家城市", "美国 阿什本"),
            ("ip", "公网 IP", ""),
            ("remote_port", "Reality 端口", "443"),
            ("socks", "本地 SOCKS", ""),
            ("http", "本地 HTTP", ""),
            ("provider", "服务商/机房", ""),
            ("panel", "3x-ui 面板 URL", ""),
            ("subscription", "订阅 URL", ""),
            ("note", "运维备注", ""),
        ]
        entries = {}
        for row, (key, label, default) in enumerate(fields):
            lab = Gtk.Label(label=label)
            lab.set_xalign(0)
            entry = Gtk.Entry()
            entry.set_text(default)
            entry.set_hexpand(True)
            grid.attach(lab, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            entries[key] = entry

        link_label = Gtk.Label(label="VLESS 链接")
        link_label.set_xalign(0)
        link_view = Gtk.TextView()
        link_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        link_view.set_monospace(True)
        link_view.set_size_request(-1, 96)
        link_scroll = Gtk.ScrolledWindow()
        link_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        link_scroll.add(link_view)
        grid.attach(link_label, 0, len(fields), 1, 1)
        grid.attach(link_scroll, 1, len(fields), 1, 1)

        hint = Gtk.Label()
        hint.set_xalign(0)
        hint.set_line_wrap(True)
        hint.set_text("说明：默认会导出本地 HTML，并把填写的 VLESS 链接接入本机 Xray 以支持托盘切换；不会自动切换生产节点，除非勾选“立即切换”。节点代码按 ISO 国家三字码 + IATA 城市码 + A 序号，例如 USA-LAX-A1、NLD-AMS-A1、SGP-SIN-A1。")
        grid.attach(hint, 0, len(fields) + 1, 2, 1)

        register_check = Gtk.CheckButton(label="导出后接入本机 Xray，并加入托盘节点列表")
        register_check.set_active(True)
        switch_check = Gtk.CheckButton(label="接入成功后立即切换到该节点")
        switch_check.set_active(False)
        grid.attach(register_check, 1, len(fields) + 2, 1, 1)
        grid.attach(switch_check, 1, len(fields) + 3, 1, 1)

        template_paths = [path for path in DEFAULT_TEMPLATE_PATHS if path.exists()]
        template_check = Gtk.CheckButton(label="基于本地 HTML 模板生成新版文档")
        template_check.set_active(bool(template_paths))
        template_label = Gtk.Label()
        template_label.set_xalign(0)
        template_label.set_line_wrap(True)

        def refresh_template_label():
            if template_paths:
                template_label.set_text("\n".join(str(path) for path in template_paths))
            else:
                template_label.set_text("未选择模板。将只导出独立新增节点台账。")

        def choose_templates(_button):
            chooser = Gtk.FileChooserDialog(
                title="选择 ArchIToken-VPN HTML 模板",
                parent=dialog,
                action=Gtk.FileChooserAction.OPEN,
            )
            chooser.add_buttons("取消", Gtk.ResponseType.CANCEL, "选择", Gtk.ResponseType.OK)
            chooser.set_select_multiple(True)
            chooser.set_current_folder(str(DOWNLOAD_DIR))
            html_filter = Gtk.FileFilter()
            html_filter.set_name("HTML 文件")
            html_filter.add_pattern("*.html")
            html_filter.add_pattern("*.htm")
            chooser.add_filter(html_filter)
            if chooser.run() == Gtk.ResponseType.OK:
                selected = [Path(name) for name in chooser.get_filenames()]
                for path in selected:
                    if path not in template_paths:
                        template_paths.append(path)
                template_check.set_active(True)
                refresh_template_label()
            chooser.destroy()

        def clear_templates(_button):
            template_paths.clear()
            template_check.set_active(False)
            refresh_template_label()

        template_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        choose_btn = Gtk.Button(label="选择模板 HTML")
        clear_btn = Gtk.Button(label="清空模板")
        choose_btn.connect("clicked", choose_templates)
        clear_btn.connect("clicked", clear_templates)
        template_box.pack_start(choose_btn, False, False, 0)
        template_box.pack_start(clear_btn, False, False, 0)
        grid.attach(template_check, 1, len(fields) + 4, 1, 1)
        grid.attach(template_box, 1, len(fields) + 5, 1, 1)
        grid.attach(template_label, 1, len(fields) + 6, 1, 1)
        refresh_template_label()

        dialog.get_content_area().pack_start(grid, True, True, 0)
        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            data = {key: entry.get_text().strip() for key, entry in entries.items()}
            buffer = link_view.get_buffer()
            data["vless"] = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).strip()
            try:
                output_path = self.export_node_html(data)
                status_lines = [f"已导出本地节点文档：\n{output_path}"]
                if template_check.get_active() and template_paths:
                    template_outputs = self.export_node_templates(data, template_paths)
                    if template_outputs:
                        status_lines.append(
                            "已基于模板生成新版 HTML：\n" + "\n".join(str(path) for path in template_outputs)
                        )
                if register_check.get_active():
                    self.register_node_for_switch(data)
                    status_lines.append("已写入节点注册表，并已注入 Xray outbound。")
                    if switch_check.get_active():
                        self.switch_registered_node(data["node_code"].upper())
                        status_lines.append("已切换到新增节点。")
            except Exception as exc:
                GLib.idle_add(self.show_dialog, "ArchIToken-VPN · 导出失败", str(exc))
            else:
                self.notify(f"节点 HTML 已导出: {output_path.name}")
                refresh_node_globals()
                GLib.idle_add(self.rebuild_menu)
                GLib.idle_add(
                    self.show_dialog,
                    "ArchIToken-VPN · 导出完成",
                    "\n\n".join(status_lines),
                )
        dialog.destroy()

    def registry_payload(self, data):
        code = data.get("node_code", "").upper()
        return {
            "label": data.get("label", ""),
            "ip": data.get("ip", ""),
            "socks": int(data["socks"]) if str(data.get("socks", "")).isdigit() else "",
            "http": int(data["http"]) if str(data.get("http", "")).isdigit() else "",
            "panel": data.get("panel", ""),
            "enabled": True,
            "note": data.get("note", ""),
            "role": data.get("role", ""),
            "remote_port": int(data["remote_port"]) if str(data.get("remote_port", "")).isdigit() else 443,
            "provider": data.get("provider", ""),
            "subscription": data.get("subscription", ""),
            "vless": data.get("vless", ""),
            "outbound": node_outbound_tag(code),
        }

    def register_node_for_switch(self, data):
        code = data.get("node_code", "").upper()
        if not data.get("vless"):
            raise ValueError("要接入 Xray 并支持托盘切换，必须填写 VLESS 链接。")
        payload = {"node_code": code, **self.registry_payload(data)}
        fd, payload_path = tempfile.mkstemp(prefix="architoken-node-", suffix=".json", dir="/tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
            result = subprocess.run(
                ["pkexec", "/usr/bin/python3", REGISTER_SCRIPT, payload_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or "注册节点失败"
                raise RuntimeError(detail)
        finally:
            try:
                os.unlink(payload_path)
            except OSError:
                pass
        save_registry_node(code, self.registry_payload(data))

    def switch_registered_node(self, code):
        result = subprocess.run(
            ["pkexec", "/usr/bin/python3", SWITCH_SCRIPT, code],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "切换新增节点失败"
            raise RuntimeError(detail)
        self.update_status()

    def export_node_html(self, data):
        node_code = data.get("node_code", "").upper()
        ip = data.get("ip", "")
        remote_port = data.get("remote_port", "443") or "443"
        self.validate_node_form(node_code, ip, remote_port)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = DOWNLOAD_DIR / f"ArchIToken-VPN-新增节点-{node_code}-{stamp}.html"
        output_path.write_text(self.render_node_html(data, stamp), encoding="utf-8")
        return output_path

    def validate_node_form(self, node_code, ip, remote_port):
        if not re.match(r"^[A-Z]{3}-[A-Z0-9]{3}-A[0-9]+$", node_code):
            raise ValueError("节点代码格式应为 ISO国家三字码-IATA城市码-A序号，例如 USA-LAX-A1。")
        if not re_match_ip(ip):
            raise ValueError("公网 IP 格式不正确。")
        if not str(remote_port).isdigit():
            raise ValueError("Reality 端口必须是数字。")

    def export_node_templates(self, data, template_paths):
        node_code = data.get("node_code", "").upper()
        self.validate_node_form(node_code, data.get("ip", ""), data.get("remote_port", "443") or "443")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        outputs = []
        for template_path in template_paths:
            path = Path(template_path)
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            updated = self.render_template_with_node(text, data, stamp, path.name)
            output_name = f"{path.stem}-新增{node_code}-{stamp}{path.suffix or '.html'}"
            output_path = DOWNLOAD_DIR / output_name
            output_path.write_text(updated, encoding="utf-8")
            outputs.append(output_path)
        return outputs

    def render_template_with_node(self, text, data, stamp, template_name):
        node_code = data.get("node_code", "").upper()
        section = self.render_template_node_section(data, stamp)
        marker = f"NODE-{node_code}"
        if self.has_marker(text, marker):
            return self.replace_marker(text, marker, section)

        if "ArchIToken-VPN · 运维管理文档" in text or "节点与二维码" in text:
            text = self.insert_after_section_heading(text, "节点与二维码", self.marked_block(marker, section))
            if data.get("subscription"):
                text = self.insert_marked_row(
                    text,
                    "订阅状态",
                    f"SUB-{node_code}",
                    f'<tr><td>{html.escape(node_code)}</td><td><code>{html.escape(data.get("subscription", ""))}</code></td><td>新增节点订阅入口；接入生产前需验证 HTTP 状态、内容格式和客户端导入效果</td></tr>',
                )
            if data.get("panel"):
                text = self.insert_marked_row(
                    text,
                    "3x-ui 面板",
                    f"PANEL-{node_code}",
                    f'<tr><th>{html.escape(node_code)}</th><td><code>{html.escape(data.get("panel", ""))}</code> · 新增节点面板；接入生产后复测出口。</td></tr>',
                    close_tag="</table>",
                )
            return text

        insert_at = text.rfind("</main>")
        if insert_at == -1:
            insert_at = text.rfind("</body>")
        if insert_at == -1:
            insert_at = len(text)
        return text[:insert_at] + self.marked_block(marker, section) + "\n" + text[insert_at:]

    def render_template_node_section(self, data, stamp):
        esc = lambda value: html.escape(str(value or ""), quote=True)
        node_code = data.get("node_code", "").upper()
        subscription = data.get("subscription", "")
        panel = data.get("panel", "")
        vless = data.get("vless", "")
        vless_block = (
            f"<details><summary>VLESS 直连链接</summary><textarea readonly>{esc(vless)}</textarea></details>"
            if vless
            else '<p class="note muted">未填写 VLESS 链接。可后续从 3x-ui 或客户端导出后补充。</p>'
        )
        subscription_row = f'<tr><th>订阅 URL</th><td><code>{esc(subscription)}</code></td></tr>' if subscription else ""
        panel_row = f'<tr><th>3x-ui 面板</th><td><code>{esc(panel)}</code></td></tr>' if panel else ""
        return f"""
  <section>
    <h2>新增节点：{esc(node_code)}</h2>
    <p><span class="pill warn">新增节点</span> <span class="pill ok">{esc(data.get("label"))}</span> <span class="pill warn">待验证后纳入生产</span></p>
    <table>
      <tr><th>节点代码</th><td><code>{esc(node_code)}</code></td></tr>
      <tr><th>国家城市</th><td>{esc(data.get("label"))}</td></tr>
      <tr><th>公网 IP</th><td><code>{esc(data.get("ip"))}</code></td></tr>
      <tr><th>Reality 端口</th><td><code>{esc(data.get("remote_port") or "443")}</code></td></tr>
      <tr><th>本地入口</th><td>SOCKS <code>{esc(data.get("socks"))}</code> · HTTP <code>{esc(data.get("http"))}</code></td></tr>
      <tr><th>服务商/机房</th><td>{esc(data.get("provider"))}</td></tr>
      {subscription_row}
      {panel_row}
      <tr><th>托盘切换</th><td>若已勾选接入本机 Xray，本节点会写入托盘节点列表；点击节点即可切换 10808/10809 自动入口。</td></tr>
      <tr><th>导出时间</th><td><code>{esc(stamp)}</code></td></tr>
      <tr><th>备注</th><td>{esc(data.get("note"))}</td></tr>
    </table>
    {vless_block}
    <p class="note muted">校验建议：先用 <code>vpn-status</code> 和 <code>curl -4 --socks5-hostname 127.0.0.1:10808 https://api.ipify.org</code> 验证出口，再发放给团队。</p>
  </section>
"""

    def marked_block(self, key, content):
        return f"\n<!-- ARCHITOKEN:{key}:BEGIN -->\n{content.strip()}\n<!-- ARCHITOKEN:{key}:END -->\n"

    def has_marker(self, text, key):
        return f"<!-- ARCHITOKEN:{key}:BEGIN -->" in text and f"<!-- ARCHITOKEN:{key}:END -->" in text

    def replace_marker(self, text, key, content):
        begin = f"<!-- ARCHITOKEN:{key}:BEGIN -->"
        end = f"<!-- ARCHITOKEN:{key}:END -->"
        start = text.find(begin)
        finish = text.find(end, start)
        if start == -1 or finish == -1:
            return text
        finish += len(end)
        return text[:start] + self.marked_block(key, content) + text[finish:]

    def section_end_after_heading(self, text, heading):
        marker = f"<h2>{heading}</h2>"
        pos = text.find(marker)
        if pos == -1:
            return -1
        end = text.find("</section>", pos)
        if end == -1:
            return -1
        return end + len("</section>")

    def insert_after_section_heading(self, text, heading, content):
        end = self.section_end_after_heading(text, heading)
        if end == -1:
            insert_at = text.rfind("</main>")
            if insert_at == -1:
                insert_at = len(text)
            return text[:insert_at] + content + text[insert_at:]
        return text[:end] + content + text[end:]

    def insert_marked_row(self, text, heading, key, row, close_tag="</tbody>"):
        if self.has_marker(text, key):
            return self.replace_marker(text, key, row)
        marker = f"<h2>{heading}</h2>"
        pos = text.find(marker)
        if pos == -1:
            return text
        insert_at = text.find(close_tag, pos)
        if insert_at == -1:
            return text
        return text[:insert_at] + self.marked_block(key, row) + text[insert_at:]

    def render_node_html(self, data, stamp):
        esc = lambda value: html.escape(str(value or ""), quote=True)
        node_code = data.get("node_code", "").upper()
        title = f"ArchIToken-VPN · 新增节点台账 · {node_code}"
        rows = [
            ("节点代码", node_code),
            ("节点角色", data.get("role")),
            ("国家城市", data.get("label")),
            ("公网 IP", data.get("ip")),
            ("Reality 端口", data.get("remote_port") or "443"),
            ("本地 SOCKS", data.get("socks")),
            ("本地 HTTP", data.get("http")),
            ("服务商/机房", data.get("provider")),
            ("3x-ui 面板", data.get("panel")),
            ("订阅 URL", data.get("subscription")),
            ("运维备注", data.get("note")),
            ("导出时间", stamp),
        ]
        table_rows = "\n".join(
            f"<tr><th>{esc(k)}</th><td>{esc(v) if not str(v).startswith(('http://', 'https://')) else '<code>' + esc(v) + '</code>'}</td></tr>"
            for k, v in rows
        )
        vless = data.get("vless", "")
        vless_block = (
            f"<textarea readonly>{esc(vless)}</textarea>"
            if vless
            else "<p class=\"muted\">未填写 VLESS 链接。可后续从 3x-ui 或客户端导出后补充。</p>"
        )
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{esc(title)}</title>
<style>
:root {{ color-scheme: dark; --bg:#0d0f14; --panel:#171a22; --panel2:#202430; --text:#f2efe7; --muted:#a8a095; --line:#303746; --gold:#d5a94f; --green:#75c77a; --red:#e06b5f; --blue:#78a6d9; font-family: Inter, "Noto Sans SC", system-ui, sans-serif; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); line-height:1.65; }}
header {{ padding:32px 42px; border-bottom:1px solid var(--line); background:#11141b; }}
main {{ max-width:1040px; margin:0 auto; padding:28px 22px 70px; }}
section {{ margin:0 0 24px; padding:22px; background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
h1 {{ margin:0 0 8px; font-size:30px; letter-spacing:0; }}
h2 {{ margin:0 0 14px; font-size:22px; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ text-align:left; vertical-align:top; border-bottom:1px solid var(--line); padding:9px 8px; }}
th {{ width:160px; color:var(--muted); font-weight:600; }}
code, textarea {{ font-family:"JetBrains Mono","SF Mono",Consolas,monospace; }}
textarea {{ width:100%; min-height:120px; padding:12px; background:#0f1118; color:var(--text); border:1px solid var(--line); border-radius:6px; resize:vertical; }}
.pill {{ display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; padding:3px 9px; white-space:nowrap; font-size:13px; margin-right:8px; }}
.ok {{ color:var(--green); border-color:rgba(117,199,122,.35); }}
.warn {{ color:var(--gold); border-color:rgba(213,169,79,.35); }}
.bad {{ color:var(--red); border-color:rgba(224,107,95,.35); }}
.muted {{ color:var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>{esc(title)}</h1>
  <div class="muted">本文件由 ArchIToken-VPN 托盘本地导出，仅用于新增节点运维台账；不会修改生产 Xray 配置。</div>
</header>
<main>
  <section>
    <h2>节点信息</h2>
    <p><span class="pill ok">{esc(node_code)}</span><span class="pill warn">待接入生产配置</span></p>
    <table>{table_rows}</table>
  </section>
  <section>
    <h2>连接链接</h2>
    {vless_block}
    <p class="muted">跨平台导入优先使用剪贴板。二维码可由客户端或 3x-ui 基于同一链接生成。</p>
  </section>
  <section>
    <h2>接入检查清单</h2>
    <table>
      <tr><th>命名规范</th><td>ISO 国家三字码 + IATA 城市码 + A 序号，例如 USA-LAX-A1、NLD-AMS-A1。</td></tr>
      <tr><th>Reality 入口</th><td>新增 VPS 的公网入站端口以实际生产配置为准；不要在未验证前替换当前 443 生产入口。</td></tr>
      <tr><th>托盘模式</th><td>全局代理用于隐私一致性和排障；国内直连用于日常访问，国内流量直连、国外流量走 Xray。</td></tr>
      <tr><th>状态灯</th><td>绿色正常，黄色预警或可切换，红色异常。</td></tr>
      <tr><th>验收命令</th><td><code>curl -4 --socks5-hostname 127.0.0.1:10808 https://api.ipify.org</code></td></tr>
    </table>
  </section>
</main>
</body>
</html>
"""
    
    def restart_service(self, widget):
        self.run_cmd("pkexec systemctl restart xray-client", timeout=15)
        if self.tun_active:
            self.run_cmd("pkexec systemctl restart architoken-xray-tun.service", timeout=15)
            self.notify("Xray 与 TUN 服务已重启")
        else:
            self.notify("Xray 服务已重启")
        threading.Thread(target=self.update_status, daemon=True).start()
    
    def copy_socks(self, widget):
        socks_port, _ = self.get_active_ports()
        text = f"127.0.0.1:{socks_port}"
        self.run_cmd(f"echo -n '{text}' | xclip -selection clipboard 2>/dev/null || echo -n '{text}' | xsel -ib 2>/dev/null")
        self.notify(f"已复制: {text}")
    
    def open_config(self, widget):
        subprocess.Popen(["gnome-terminal", "--", "bash", "-c", "sudo nano /etc/xray-client/config.json; read -p '按回车关闭...'"])
    
    def open_log(self, widget):
        subprocess.Popen(["gnome-terminal", "--", "bash", "-c", "sudo journalctl -u xray-client -u architoken-xray-tun.service -f"])

    def check_remote_port(self, host, port, timeout=3):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False
    
    def open_panel(self, widget):
        code = self.get_active_node_code()
        node = NODES.get(code, NODES[DEFAULT_NODE])
        self.active_node = code
        if not self.check_remote_port(node["ip"], 2053):
            msg = (
                f"当前节点 {code} · {node['ip']} 的 3x-ui 面板端口 2053 不可达。\n\n"
                "不会自动打开 USA-LAX-A1 面板，以免把当前节点误判成美国节点。\n"
                "这通常表示该 VPS 没有部署 3x-ui 面板，或防火墙没有开放 2053。"
            )
            self.notify(f"当前节点面板不可达 → {code}")
            GLib.idle_add(self.show_dialog, "ArchIToken-VPN · 面板不可达", msg)
            return
        self.notify(f"打开 3x-ui 面板 → {code} · {node['ip']}")
        subprocess.Popen(["xdg-open", node["panel"]])

    def open_webrtc_check(self, widget):
        if not WEBRTC_CHECK.exists():
            self.notify(f"WebRTC 检测页不存在: {WEBRTC_CHECK}")
            return
        self.ensure_webrtc_server()
        subprocess.Popen(["xdg-open", WEBRTC_URL])
    
    def notify(self, msg):
        subprocess.Popen(["notify-send", "ArchIToken-VPN", msg, "-i", "network-vpn"])
    
    def quit(self, widget):
        Gtk.main_quit()

if __name__ == "__main__":
    try:
        current_pid = os.getpid()
        result = subprocess.run(
            ["ps", "-C", "python3", "-o", "pid=,args="],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            pid = int(parts[0])
            if pid != current_pid and SCRIPT_PATH in parts[1]:
                os.kill(pid, signal.SIGTERM)
        time.sleep(0.2)
    except Exception:
        pass
    app = ArchITokenVPNTray()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
