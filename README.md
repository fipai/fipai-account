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

## 数据库

使用 SQLite 开发，PostgreSQL 生产（`USE_POSTGRES=true` 环境变量切换）
