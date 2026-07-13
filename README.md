# WS -> OSC 转发服务

WebSocket 到 OSC 协议转换服务，支持中文参数（Ventuz OSC兼容）。

## 功能

- 接收 WebSocket JSON 消息
- 转换为 OSC Bundle 并通过 UDP 发送
- 支持中文参数（BEUC编码，兼容Ventuz）
- 系统托盘运行，带调试日志窗口

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python websocket_to_osc.py
```

程序启动后自动最小化到系统托盘，右键托盘图标可打开调试窗口或退出。

### 打包为 EXE

```bash
build.bat
```

生成文件：`dist/WS_OSC_Server.exe`

## 消息格式

### 请求（OSC，兼容旧格式）

```json
{
  "ip": "230.230.230.235",
  "port": 8001,
  "address": "/iPad",
  "args": ["欢迎词", "欢迎光临"]
}
```

### 请求（普通 UDP 文本）

```json
{
  "protocol": "udp",
  "ip": "127.0.0.1",
  "port": 2756,
  "payload": "ALL_ON"
}
```

### 响应

成功：
```json
{
  "ok": true,
  "target": "230.230.230.235:8001",
  "address": "/iPad",
  "args_count": 2
}
```

UDP 成功：
```json
{
  "ok": true,
  "target": "127.0.0.1:2756",
  "protocol": "udp",
  "bytes_sent": 6
}
```

失败：
```json
{
  "ok": false,
  "error": "缺少目标 IP"
}
```

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `protocol` | string | 否 | 协议类型，`osc` 或 `udp`，默认 `osc` |
| `ip` | string | 是 | 目标IP（支持别名 `target_ip`） |
| `port` | number | 是 | 目标端口 1-65535 |
| `address` | string | OSC时是 | OSC地址，以`/`开头（支持别名 `osc_address`） |
| `args` | array | 否 | OSC参数数组，支持 int/float/string/bool |
| `payload` | string | UDP时是 | 普通 UDP 文本内容，按 UTF-8 编码发送 |

## 协议说明

- 未传 `protocol` 时，默认按 `OSC` 处理，兼容旧 JSON。
- `protocol: "osc"` 时，使用 `address` + `args` 组装 OSC Bundle 后通过 UDP 发送。
- `protocol: "udp"` 时，直接把 `payload` 按 UTF-8 编码后通过 UDP 发送，不做 OSC 封装。

兼容旧格式示例：

```json
{"ip":"230.230.230.235","port":8010,"address":"/iPad","args":["黑场"]}
```

## 参数类型

| JSON类型 | OSC类型 |
|----------|---------|
| `123` | int |
| `3.14` | float |
| `"hello"` | string |
| `"中文"` | BEUC (Ventuz兼容) |
| `true/false` | int (1/0) |

## WebSocket 连接

```
ws://127.0.0.1:7200
```

## 项目结构

```
osc/
├── websocket_to_osc.py    # 主程序
├── requirements.txt       # Python依赖
├── build.bat             # 打包脚本
├── .gitignore
└── README.md
```

## 开发

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python websocket_to_osc.py
```

## License

MIT
