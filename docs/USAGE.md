## SmartThingsAPI 使用文档（本地 / 服务器）

---

### 0) 统一返回格式（客户端解析契约）

所有 JSON 返回统一为：

- 成功：`{"code": 200, "msg": "", "data": ...}`
- 失败：`{"code": <非200>, "msg": "错误信息", "data": <错误细节>}`

客户端只需要判断 `code==200`；否则读取 `msg` 展示错误信息，必要时结合 `data` 做更细分处理。

---

### 1) 本地启动（开发）

#### 1.1 安装依赖

```bash
cd /path/to/SmartThingsAPI
./venv/bin/pip install -r requirements.txt
```

#### 1.2 启动服务

```bash
cd /path/to/SmartThingsAPI
./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### 1.3 健康检查

```bash
curl "http://127.0.0.1:8000/health"
```

---

### 2) SaaS 模式（多用户）最小跑通流程

> SaaS 模式下：客户端调用你服务用 `X-API-Key` 鉴权；SmartThings token 存在服务端数据库；服务端自动 refresh。

#### 2.1 创建用户（拿到 X-API-Key）

```bash
curl -X POST "http://127.0.0.1:8000/users/signup" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
```

返回的 `data.apiKey` 就是后续请求要带的：
- `X-API-Key: <apiKey>`

#### 2.2 发起 SmartThings OAuth 授权（跳转）

```bash
curl -v "http://127.0.0.1:8000/oauth/smartthings/authorize" \
  -H "X-API-Key: <apiKey>"
```

浏览器完成三星账号登录授权后，SmartThings 会回调：
- `GET /oauth/smartthings/callback?code=...&state=...`

服务端会把 token 写入数据库。

#### 2.3 验证 SmartThings token 可用

```bash
curl "http://127.0.0.1:8000/auth/validate" \
  -H "X-API-Key: <apiKey>"
```

---

### 3) 设备发现与控制（电视/空调）

#### 3.1 列设备

```bash
curl "http://127.0.0.1:8000/devices" \
  -H "X-API-Key: <apiKey>"
```

#### 3.2 看设备支持哪些能力（建议先做）

```bash
curl "http://127.0.0.1:8000/devices/<device_id>/capabilities" \
  -H "X-API-Key: <apiKey>"
```

#### 3.3 空调（aircon）

```bash
curl -X POST "http://127.0.0.1:8000/aircon/<device_id>/power" \
  -H "X-API-Key: <apiKey>" \
  -H "Content-Type: application/json" \
  -d '{"on": true}'
```

#### 3.4 电视（tv）

```bash
curl -X POST "http://127.0.0.1:8000/tv/<device_id>/volume" \
  -H "X-API-Key: <apiKey>" \
  -H "Content-Type: application/json" \
  -d '{"level": 15}'
```

遥控按键（不同电视 payload 可能不同）：

```bash
# 默认：arguments=[{"keyCode":"KEY_VOLUP"}]
curl -X POST "http://127.0.0.1:8000/tv/<device_id>/key" \
  -H "X-API-Key: <apiKey>" \
  -H "Content-Type: application/json" \
  -d '{"key":"KEY_VOLUP"}'
```

---

### 4) 服务器部署时的数据库（Ubuntu 22.04 推荐 Postgres）

#### 4.1 Postgres 安装（Ubuntu 22.04）

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
pg_lsclusters
```

看到 `online` 即表示数据库已运行。

#### 4.2 创建数据库用户/数据库

```bash
sudo -u postgres psql
```

在 `postgres=#` 执行（密码不要包含 `!`，避免 shell 历史展开问题；或记得正确引用）：

```sql
CREATE USER smartthingsapi WITH PASSWORD 'StApi2026StrongPwd';
CREATE DATABASE smartthingsapi OWNER smartthingsapi;
GRANT ALL PRIVILEGES ON DATABASE smartthingsapi TO smartthingsapi;
\q
```

验证：

```bash
export PGPASSWORD='StApi2026StrongPwd'
psql -h 127.0.0.1 -U smartthingsapi -d smartthingsapi -c "select 1;"
unset PGPASSWORD
```

#### 4.3 服务端连接串（写到服务器上的 `.env`）

你需要在服务器项目目录（例如 `/opt/smartthingsapi/.env`）里写：

```env
APP_ENV=prod
DATABASE_URL=postgresql+psycopg2://smartthingsapi:StApi2026StrongPwd@127.0.0.1:5432/smartthingsapi
API_KEY_PEPPER=prod-CHANGE-ME
OAUTH_STATE_SECRET=prod-CHANGE-ME-TOO
SMARTTHINGS_CLIENT_ID=...
SMARTTHINGS_CLIENT_SECRET=...
SMARTTHINGS_REDIRECT_URI=https://your-domain.com/oauth/smartthings/callback
CORS_ALLOW_ORIGINS=https://your-frontend.com
```

注意：本项目 `requirements.txt` 已包含 `psycopg2-binary`，用于支持 `postgresql+psycopg2://`。

---

### 5) SmartThings SmartApp WebHook（Target URL 填什么）

当你在 SmartThings Developer Workspace 创建 “自动化 / SmartApp（WebHook 端点）” 时，页面会要求你填写 **目标网址（Target URL）**。

- **你应该填写**：
  - `https://glowlabwall.com/smartthings/smartapp`

本项目已实现该端点：
- `POST /smartthings/smartapp`
  - 支持 SmartThings 的 `CONFIRMATION` / `PING` lifecycle（用于通过 SmartThings 的 WebHook 验证）

注意：这是 SmartApp 的 lifecycle webhook，不是我们客户端调用的接口；它返回的是 SmartThings 要求的“原始 lifecycle JSON”，不会走 `code/msg/data` 包装。

---

### 6) 服务器上 Nginx 反代（让 `https://glowlabwall.com/...` 打到 FastAPI）

你现在如果执行：

```bash
curl -I https://glowlabwall.com/
curl -I https://glowlabwall.com/smartthings/smartapp
```

- `/` 返回 200 且 `Server: nginx/...`：说明 **Nginx 对外通了**
- `/smartthings/smartapp` 返回 **404**：说明 **这个路径还没反代到 FastAPI**（还在走静态站点/默认站点）

#### 6.1 推荐做法：只反代 API 相关路径（保留你现有的静态首页）

在你的站点配置（常见是 `/etc/nginx/sites-available/<your-site>`）里，给 `server {}` 增加这些 `location`：

```nginx
# SmartApp lifecycle webhook
location /smartthings/ {
  proxy_pass http://127.0.0.1:8000;
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
}

# OAuth 回调与跳转
location /oauth/ {
  proxy_pass http://127.0.0.1:8000;
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
}

# 业务 API（用户/设备/控制）
location ~ ^/(users|devices|aircon|tv|auth)(/|$) {
  proxy_pass http://127.0.0.1:8000;
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
}
```

> 备注：你用 `curl -I` 发的是 **HEAD** 请求，而本项目的 `POST /smartthings/smartapp` 只允许 POST；因此当反代正确后，`curl -I https://.../smartthings/smartapp` 可能会变成 **405 Method Not Allowed**（这是正常现象）。

#### 6.2 重新加载 Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

#### 6.3 验证 SmartApp WebHook 端点是否真正打到 FastAPI

用 POST 模拟 SmartThings 的 PING（必须 POST）：

```bash
curl -i -X POST "https://glowlabwall.com/smartthings/smartapp" \
  -H "Content-Type: application/json" \
  -d '{"lifecycle":"PING","pingData":{"challenge":"abc"}}'
```

预期返回（原始 JSON，不带 `code/msg/data` 包装）：

```json
{"pingData":{"challenge":"abc"}}
```

---

### 7) 生产常驻运行（systemd 自启，不用手动开着终端）

> 你如果只是 `kill` 掉 uvicorn，而没有配置 systemd，自然不会“自动再次启动”。生产建议用 systemd 常驻管理。

#### 7.1 创建 systemd service

在服务器创建文件：`/etc/systemd/system/smartthingsapi.service`

```ini
[Unit]
Description=SmartThingsAPI (FastAPI/Uvicorn)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/smartthingsapi/SmartThingsAPI
EnvironmentFile=/opt/smartthingsapi/SmartThingsAPI/.env
ExecStart=/opt/smartthingsapi/SmartThingsAPI/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=2

# 生产可按需收紧权限（可选）
User=root
Group=root

[Install]
WantedBy=multi-user.target
```

#### 7.2 启用并启动

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now smartthingsapi
sudo systemctl status smartthingsapi --no-pager
```

#### 7.3 看日志

```bash
sudo journalctl -u smartthingsapi -f
```

#### 7.4 验证是否在监听 8000

```bash
sudo ss -lntp | grep ':8000' || echo "8000 not listening"
curl -i https://glowlabwall.com/users/me
```
