## SmartThingsAPI（Python 服务端）

这是一个用 **FastAPI** 封装三星 **SmartThings REST API** 的服务端项目。你在服务端配置好 `SMARTTHINGS_TOKEN` 后，就可以通过本服务的 HTTP 接口去：

- 列出设备
- 查询设备详情/状态
- 下发设备 commands

### 使用文档

- 详细使用手册：`docs/USAGE.md`

### 环境变量（开发/生产）

通过 `APP_ENV=dev|prod` 区分环境：
- **dev**：默认开启 `/docs`、`/openapi.json`
- **prod**：默认关闭 `/docs`、`/openapi.json`（更安全）

必填（生产必须配置）：
- **DATABASE_URL**：数据库连接串（开发默认：`sqlite:///./smartthingsapi.db`；生产建议 Postgres）
- **API_KEY_PEPPER**：用于哈希保存 API Key 的 pepper（生产必须改掉）
- **OAUTH_STATE_SECRET**：用于签名 OAuth state（生产必须改掉）

SmartThings 相关：
- **SMARTTHINGS_CLIENT_ID / SMARTTHINGS_CLIENT_SECRET / SMARTTHINGS_REDIRECT_URI**：SmartThings OAuth 配置（SaaS 绑定用户必需）
- **SMARTTHINGS_OAUTH_SCOPE**：默认 `r:devices:* x:devices:* r:locations:*`
- **SMARTTHINGS_BASE_URL**：默认 `https://api.smartthings.com/v1`
- **SMARTTHINGS_TIMEOUT_S**：默认 `15`

可选（仅单用户/自用兜底）：
- **SMARTTHINGS_TOKEN**：PAT（SaaS 建议不要用这个，而是走 OAuth 绑定）

示例环境文件：
- `example.dev.env`
- `example.prod.env`

你也可以创建 `.env` 文件（项目根目录），参考 `example.env`：

```env
SMARTTHINGS_TOKEN=your_pat_here
```

### SmartThings “登录/鉴权”说明（本项目实现了什么）

- **SmartThings 官方 API 的鉴权**：主要是 `Authorization: Bearer <token>`。
- **本项目（SaaS）当前实现**：
  - 你的平台给每个用户发放一个 **X-API-Key**
  - 用户通过 `/oauth/smartthings/authorize` 跳转到 SmartThings 完成授权
  - SmartThings 回调 `/oauth/smartthings/callback` 后，本服务把 **该用户的 access_token/refresh_token** 存进数据库
  - 后续控制接口只需要带 `X-API-Key`，本服务会自动用该用户绑定的 token 去调用 SmartThings

### Token 过期与刷新（SaaS）

- **OAuth 模式（SaaS）**：本服务会在请求时检测 `expires_at`，如果 access token 已过期/即将过期且有 `refresh_token`，会自动向 SmartThings 刷新并更新数据库。
- **PAT 模式**：PAT 通常是长效的，但一旦被撤销/失效只能重新生成；不存在 refresh_token 自动刷新这一说。

### 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

生产启动（示例）：

```bash
APP_ENV=prod uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 接口示例

### 统一返回格式（客户端解析契约）

- **成功**：
  - `{"code": 200, "msg": "", "data": <payload>}`
- **失败**：
  - `{"code": <非200>, "msg": "错误信息", "data": <错误细节>}`

客户端只需要判断 `code==200`；否则读取 `msg` 展示错误信息，必要时结合 `data` 做更细分处理。

- 健康检查：`GET /health`
- Token 验证：`GET /auth/validate`
- 创建用户（发放 API Key）：`POST /users/signup`
- 当前用户：`GET /users/me`
- SmartThings OAuth（跳转授权）：`GET /oauth/smartthings/authorize`
- SmartThings OAuth（回调）：`GET /oauth/smartthings/callback`
- 设备列表：`GET /devices`
- 设备详情：`GET /devices/{device_id}`
- 设备状态：`GET /devices/{device_id}/status`
- 能力摘要：`GET /devices/{device_id}/capabilities`
- 下发命令：`POST /devices/{device_id}/commands`

#### 空调（aircon）

- 电源：`POST /aircon/{device_id}/power`
- 模式：`POST /aircon/{device_id}/mode`
- 温度：`POST /aircon/{device_id}/temperature`
- 风速：`POST /aircon/{device_id}/fan-speed`

#### 电视（tv）

- 电源：`POST /tv/{device_id}/power`
- 音量：`POST /tv/{device_id}/volume`
- 音量步进：`POST /tv/{device_id}/volume-step`
- 静音：`POST /tv/{device_id}/mute`
- 频道：`POST /tv/{device_id}/channel`
- 频道步进：`POST /tv/{device_id}/channel-step`
- 信源：`POST /tv/{device_id}/input-source`
- 遥控按键：`POST /tv/{device_id}/key`

命令示例（开关灯等能力以你的设备为准）：

```bash
curl -X POST "http://localhost:8000/devices/<device_id>/commands" \
  -H "Content-Type: application/json" \
  -d '{
    "commands": [
      {
        "component": "main",
        "capability": "switch",
        "command": "on"
      }
    ]
  }'
```

电视遥控按键示例（不同电视可能 payload 不同）：

```bash
# 常见写法 1：arguments=[{"keyCode": "KEY_VOLUP"}]（默认）
curl -X POST "http://localhost:8000/tv/<device_id>/key" \
  -H "Content-Type: application/json" \
  -d '{"key":"KEY_VOLUP"}'

# 常见写法 2：arguments=["KEY_VOLUP"]
curl -X POST "http://localhost:8000/tv/<device_id>/key" \
  -H "Content-Type: application/json" \
  -d '{"key":"KEY_VOLUP","payload_style":"string"}'
```

### SaaS 最小联调流程（建议）

1) 创建用户拿 API Key：

```bash
curl -X POST "http://localhost:8000/users/signup" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
```

2) 用 API Key 发起 SmartThings 绑定（会 302 跳转到 SmartThings）：

```bash
curl -v "http://localhost:8000/oauth/smartthings/authorize" \
  -H "X-API-Key: <api_key_from_signup>"
```

3) 授权成功后，SmartThings 会回调 `SMARTTHINGS_REDIRECT_URI`，本服务会把 token 存到数据库；之后调用控制接口时只需要带：
`X-API-Key: <api_key>`

