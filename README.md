# FIP.AI Account System

账号系统服务 (account.fipai.cn)

## 功能

- 用户注册/登录 (JWT)
- 手机号认证注册/登录
- 租户管理
- 套餐订阅
- 团队管理
- 阿里云 SMS 短信服务

## 启动

```bash
cd account/fipai-account
source venv/bin/activate
python manage.py runserver 8001
```

## 手机号认证流程

### 1. 发送验证码

```bash
POST /api/auth/send-code/
Body: { "phone": "13800000000", "purpose": "register|login" }
```

- `purpose=register`: 注册时使用
- `purpose=login`: 登录时使用
- 验证码 5 分钟内有效，每天每手机号最多发送 10 次

### 2. 手机号注册

```bash
POST /api/auth/register/phone/
Body: { "phone": "13800000000", "code": "123456", "password": "xxx" }
```

返回 JWT Token:
```json
{
  "access": "<jwt_access_token>",
  "refresh": "<jwt_refresh_token>"
}
```

### 3. 手机号登录

```bash
POST /api/auth/login/phone/
Body: { "phone": "13800000000", "code": "123456" }
```

### 4. 密码登录

```bash
POST /api/auth/login/
Body: { "username": "13800000000", "password": "xxx" }
```

username 可以是手机号或邮箱。

## SMS 配置

### 开发环境（Mock 模式）

默认使用 Mock 模式，不真实发送短信：

```bash
ALIBABA_SMS_ACCESS_KEY_ID=your_access_key
ALIBABA_SMS_ACCESS_KEY_SECRET=your_secret
ALIBABA_SMS_SIGN_NAME=FIPAI
ALIBABA_SMS_TEMPLATE_CODE=SMS_xxxxx
ALIBABA_SMS_SANDBOX=true  # 开发环境设为 true
```

### 生产环境

```bash
ALIBABA_SMS_SANDBOX=false
```

确保已配置真实的阿里云凭证。

## API 端点

### 认证

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/auth/send-code/ | 发送短信验证码 |
| POST | /api/auth/register/phone/ | 手机号注册 |
| POST | /api/auth/login/phone/ | 手机号登录 |
| POST | /api/auth/login/ | 密码登录 |
| GET | /api/auth/me/ | 获取当前用户信息 |
| POST | /api/auth/token/refresh/ | 刷新 Token |
| POST | /api/auth/logout/ | 登出 |
| PATCH | /api/auth/profile/ | 更新个人资料 |
| POST | /api/auth/password/ | 修改密码 |

### 订阅

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/subscriptions/plans/ | 获取套餐列表（按产品分组） |
| POST | /api/subscriptions/ | 订阅套餐 |
| GET | /api/subscriptions/ | 我的订阅列表 |
| POST | /api/subscriptions/{id}/activate/ | 开通订阅（创建租户） |
| POST | /api/subscriptions/{id}/cancel/ | 取消订阅 |
| GET | /api/subscriptions/active/ | 获取活跃订阅 |

### 租户

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/tenants/ | 我的租户列表 |
| POST | /api/tenants/ | 创建租户 |
| GET | /api/tenants/{id}/ | 获取租户详情 |
| PUT | /api/tenants/{id}/ | 更新租户 |
| DELETE | /api/tenants/{id}/ | 删除租户 |
| GET | /api/tenants/{id}/members/ | 获取租户成员 |
| POST | /api/tenants/{id}/invite/ | 邀请成员 |

### 团队邀请

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/teams/invitations/ | 我的邀请列表 |
| POST | /api/teams/invitations/accept/ | 接受邀请 |
| POST | /api/teams/invitations/{id}/cancel/ | 取消邀请 |

## 服务 JWT 运维发放

服务 JWT 不通过公开 HTTP API 发放。部署或密钥管理流程可在 Account 环境中执行：

```bash
python manage.py issue_service_token \
  --service decisionops \
  --tenant-id 123 \
  --scope businessbuilder
```

命令只接受 `FIP_SERVICE_JWT_ALLOWLIST` 中配置的服务和产品 scope，并要求租户处于 active 状态。Token 使用 `FIP_SERVICE_JWT_LIFETIME_SECONDS` 的短时有效期，只输出一次到标准输出，不写入数据库或日志；下游服务应通过 secret manager 注入 `DECISIONOPS_BIZGEN_SERVICE_TOKEN`、`DATACOGNIS_SERVICE_TOKEN` 等配置。

## 数据库

使用 SQLite 开发，PostgreSQL 生产（`USE_POSTGRES=true` 环境变量切换）

## 支付回调并发验证

支付回调通过 PostgreSQL `SELECT ... FOR UPDATE` 串行化同一订单的状态转换。执行 `python manage.py test tests.test_payment_concurrency` 可运行真实并发集成测试；测试在非 PostgreSQL 数据库上会明确跳过。本机 SQLite 不提供与 PostgreSQL 相同的行级锁语义，因此 SQLite 测试不能证明同单并发只激活一次。

## 认证并发验证

Refresh 轮换和 2FA challenge 消费通过 PostgreSQL `SELECT ... FOR UPDATE` 串行化。执行 `python manage.py test tests.test_auth_concurrency` 可运行并发集成测试；测试在非 PostgreSQL 数据库上会明确跳过。本机 SQLite 仅完成全部串行 Account 回归，不能证明 PostgreSQL 行级锁下的并发行为。

## TOTP 加密密钥轮换

轮换时只通过 secret manager/环境变量配置 active key 和 decrypt-only 旧 key，禁止把原始 key 放进命令行。先预检，再重封装，最后执行退役门禁：

```bash
python manage.py rewrap_totp_secrets --report
python manage.py rewrap_totp_secrets --from-key-id account-totp-2026-01 --dry-run
python manage.py rewrap_totp_secrets --from-key-id account-totp-2026-01 --batch-size 500
python manage.py rewrap_totp_secrets --check-retirement account-totp-2026-01
```

只有退役门禁成功后，才能从 `TOTP_PREVIOUS_ENCRYPTION_KEYS` 删除旧 key。明文、未知 key、畸形或无法认证的密文都会使命令以非零状态退出；输出不会包含 key、明文或密文。

## PostgreSQL 生产放行 gate

使用一次性 PostgreSQL 实例并在启动进程前注入 `USE_POSTGRES=true`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`、`DB_HOST`、`DB_PORT`。脚本不会打印密码，Django 测试运行器会创建并销毁测试数据库：

```bash
./scripts/postgres_gate.sh          # 并发与迁移专项测试
./scripts/postgres_gate.sh --full   # PostgreSQL 上执行完整 Account 测试
```

可通过 `PYTHON_BIN=/absolute/path/to/python` 指定 Python。变量缺失、SQLite 配置、占位密码或无效端口会在连接前直接失败。
