import asyncio
import json
import struct
import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, font as tkfont
from datetime import datetime
from queue import Queue
from io import BytesIO

import pystray
from PIL import Image, ImageDraw
from websockets.server import serve

WS_PORT = 7200

log_queue = Queue()


def log(level: str, msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    line = f"{timestamp} - {level} - {msg}"
    log_queue.put(line)


def create_icon_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill="#0078d4")
    draw.text((14, 14), "WS", fill="white")
    draw.text((12, 34), "OSC", fill="white")
    return img


def is_contains_chinese(s: str) -> bool:
    for char in s:
        if ord(char) > 127:
            return True
    return False


def encode_osc_string(s: str) -> bytes:
    encoded = s.encode('utf-8') + b'\x00'
    padding = (4 - len(encoded) % 4) % 4
    return encoded + b'\x00' * padding


def encode_osc_int(value: int) -> bytes:
    return struct.pack('>i', value)


def encode_osc_float(value: float) -> bytes:
    return struct.pack('>f', value)


def encode_osc_bundle(*elements: bytes) -> bytes:
    bundle_header = b'#bundle\x00'
    timetag = struct.pack('>Q', 1)
    msg = bundle_header + timetag
    for elem in elements:
        msg += struct.pack('>I', len(elem)) + elem
    return msg


def pad_to_4(data: bytes) -> bytes:
    padding = (4 - len(data) % 4) % 4
    return data + b'\x00' * padding


def encode_osc_element(address: str, args: list) -> bytes:
    address_bytes = encode_osc_string(address)
    type_tags = ','
    data = b''

    for arg in args:
        if isinstance(arg, bool):
            arg_int = 1 if arg else 0
            type_tags += 'i'
            data += encode_osc_int(arg_int)
        elif isinstance(arg, int):
            type_tags += 'i'
            data += encode_osc_int(arg)
        elif isinstance(arg, float):
            type_tags += 'f'
            data += encode_osc_float(arg)
        elif isinstance(arg, str):
            if is_contains_chinese(arg):
                type_tags += 'b'
                unicode_bytes = arg.encode('utf-16-be')
                beuc_data = b'BEUC' + unicode_bytes
                data += struct.pack('>I', len(beuc_data)) + pad_to_4(beuc_data)
            else:
                type_tags += 's'
                data += encode_osc_string(arg)
        else:
            arg_str = str(arg)
            type_tags += 's'
            data += encode_osc_string(arg_str)

    type_tag_bytes = encode_osc_string(type_tags)
    return address_bytes + type_tag_bytes + data


def send_osc(ip: str, port: int, address: str, args: list):
    element = encode_osc_element(address, args)
    bundle = encode_osc_bundle(element)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(bundle, (ip, port))
    finally:
        sock.close()


def validate_message(data: dict) -> tuple[bool, str]:
    ip = data.get('ip') or data.get('target_ip')
    if not ip:
        return False, "缺少目标 IP"

    port = data.get('port')
    if not isinstance(port, int) or not (1 <= port <= 65535):
        return False, "目标端口必须在 1-65535 范围内"

    address = data.get('address') or data.get('osc_address')
    if not address:
        return False, "缺少 OSC 地址"
    if not address.startswith('/'):
        return False, "OSC 地址必须以 / 开头"

    args = data.get('args', [])
    if not isinstance(args, list):
        return False, "args 必须是数组"

    return True, ""


async def handle_client(websocket):
    client_ip = websocket.remote_address[0] if websocket.remote_address else "未知"
    log("INFO", f"[ws_osc_server] 客户端连接: {client_ip}")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                resp = {"ok": False, "error": "消息必须是 JSON 格式"}
                await websocket.send(json.dumps(resp, ensure_ascii=False))
                log("WARN", f"[ws_osc_server] 消息格式错误: {message[:50]}...")
                continue

            if not isinstance(data, dict):
                resp = {"ok": False, "error": "消息体必须是 JSON 对象"}
                await websocket.send(json.dumps(resp, ensure_ascii=False))
                continue

            valid, error = validate_message(data)
            if not valid:
                resp = {"ok": False, "error": error}
                await websocket.send(json.dumps(resp, ensure_ascii=False))
                log("WARN", f"[ws_osc_server] 验证失败: {error}")
                continue

            ip = data.get('ip') or data.get('target_ip')
            port = data['port']
            address = data.get('address') or data.get('osc_address')
            args = data.get('args', [])

            send_osc(ip, port, address, args)
            log("INFO", f"[ws_osc_server] WS->OSC forwarded {client_ip} -> {ip}:{port} {address} {args}")

            resp = {
                "ok": True,
                "target": f"{ip}:{port}",
                "address": address,
                "args_count": len(args)
            }
            await websocket.send(json.dumps(resp, ensure_ascii=False))

    except Exception as e:
        if "close frame" in str(e):
            log("INFO", f"[ws_osc_server] 客户端断开连接: {client_ip}")
        else:
            log("ERROR", f"[ws_osc_server] 处理消息错误: {e}")


async def main():
    log("INFO", f"[ws_osc_server] WebSocket服务器启动，端口: {WS_PORT}")
    async with serve(handle_client, "0.0.0.0", WS_PORT):
        await asyncio.Future()


def run_server():
    asyncio.run(main())


class LogViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("WS -> OSC 转发服务")
        self.root.geometry("900x520")
        self.root.minsize(700, 350)
        self.root.configure(bg="#1e1e1e")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        header = tk.Frame(root, bg="#2d2d2d", height=44)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title_font = tkfont.Font(family="Microsoft YaHei UI", size=12, weight="bold")
        tk.Label(
            header,
            text="  WS -> OSC Server",
            font=title_font,
            bg="#2d2d2d",
            fg="#dcdcdc",
            anchor="w",
        ).pack(side=tk.LEFT, padx=8)

        self.status_label = tk.Label(
            header,
            text=f"listening :{WS_PORT}",
            font=("Consolas", 10),
            bg="#2d2d2d",
            fg="#6a9955",
            anchor="e",
        )
        self.status_label.pack(side=tk.RIGHT, padx=12)

        toolbar = tk.Frame(root, bg="#252526", height=32)
        toolbar.pack(fill=tk.X)
        toolbar.pack_propagate(False)

        btn_clear = tk.Button(
            toolbar,
            text="Clear",
            font=("Microsoft YaHei UI", 9),
            bg="#3c3c3c",
            fg="#cccccc",
            activebackground="#505050",
            activeforeground="#ffffff",
            bd=0,
            padx=10,
            command=self.clear_log,
        )
        btn_clear.pack(side=tk.LEFT, padx=6, pady=4)

        self.auto_scroll_var = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(
            toolbar,
            text="Auto Scroll",
            font=("Microsoft YaHei UI", 9),
            bg="#252526",
            fg="#cccccc",
            selectcolor="#3c3c3c",
            activebackground="#252526",
            activeforeground="#cccccc",
            variable=self.auto_scroll_var,
        )
        cb.pack(side=tk.LEFT, padx=6)

        self.count_label = tk.Label(
            toolbar,
            text="0 msgs",
            font=("Consolas", 9),
            bg="#252526",
            fg="#808080",
            anchor="e",
        )
        self.count_label.pack(side=tk.RIGHT, padx=12)

        text_frame = tk.Frame(root, bg="#1e1e1e")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self.text = scrolledtext.ScrolledText(
            text_frame,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            selectbackground="#264f78",
            wrap=tk.WORD,
            state=tk.DISABLED,
            borderwidth=0,
            highlightthickness=0,
        )
        self.text.pack(fill=tk.BOTH, expand=True)

        self.text.tag_configure("INFO", foreground="#d4d4d4")
        self.text.tag_configure("WARN", foreground="#dcdcaa")
        self.text.tag_configure("ERROR", foreground="#f44747")

        self.msg_count = 0
        self.tray_icon = None
        self.visible = True
        self.poll_queue()

    def on_close(self):
        self.root.withdraw()
        self.visible = False

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.visible = True

    def quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    def clear_log(self):
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)
        self.msg_count = 0
        self.count_label.config(text="0 msgs")

    def append_log(self, line: str):
        self.msg_count += 1
        self.count_label.config(text=f"{self.msg_count} msgs")

        tag = "INFO"
        if "WARN" in line:
            tag = "WARN"
        elif "ERROR" in line:
            tag = "ERROR"

        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, line + "\n", tag)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def poll_queue(self):
        while not log_queue.empty():
            self.append_log(log_queue.get())
        if self.auto_scroll_var.get():
            self.text.see(tk.END)
        self.root.after(100, self.poll_queue)


def setup_tray(app: LogViewer):
    def on_show(icon, item):
        app.root.after(0, app.show_window)

    def on_exit(icon, item):
        app.root.after(0, app.quit_app)

    icon_image = create_icon_image()
    menu = pystray.Menu(
        pystray.MenuItem("打开调试窗口", on_show, default=True),
        pystray.MenuItem("退出", on_exit),
    )

    tray_icon = pystray.Icon(
        "WS_OSC",
        icon_image,
        "WS -> OSC 转发服务",
        menu,
    )
    app.tray_icon = tray_icon
    return tray_icon


if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    root = tk.Tk()
    root.withdraw()
    app = LogViewer(root)
    app.visible = False

    tray_icon = setup_tray(app)

    tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()

    log("INFO", "[ws_osc_server] 服务已启动，最小化到系统托盘")

    root.mainloop()
