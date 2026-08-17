# Agent-Account Sprint 3 开发计划

> 制定日期: 2026-08-17
> 负责人: Agent-Account

---

## 一、当前状态（Sprint 2 完成后）

### 1.1 Sprint 2 完成情况

根据 `DEVELOPMENT_PLAN_SPRINT2.md` 和 ROADMAP.md 记录：

| 模块 | 状态 | 说明 |
|------|------|------|
| Task 1: 文档同步 | ✅ 已完成 | README.md 已更新为手机号认证流程 |
| Task 2: API 端点完整性测试 | ✅ 已通过 | `tests/test_full_contract_e2e.py` (21 tests) |
| Task 3: JWT Token Claims 验证 | ✅ 已通过 | `tests/test_jwt_claims.py` (6 tests) |
| Task 4: 订阅状态机契约测试 | ✅ 已通过 | `tests/test_subscription_state_machine.py` (11 tests) |
| Task 5: 安全基线回归测试 | ✅ 已通过 | 49 tests total passed |

### 1.2 Sprint 2 测试汇总

```
cd account/fipai-account && ./venv/bin/python manage.py test tests/ -v 2
- tests/test_review_2026_07_07_account.py: 7 passed
- tests/test_settings_security.py: 4 passed
- tests/test_full_contract_e2e.py: 21 passed
- tests/test_jwt_claims.py: 6 passed
- tests/test_subscription_state_machine.py: 11 passed
Total: 49 passed
```

### 1.3 当前代码完整性

| 模块 | 文件 | 状态 |
|------|------|------|
| SMSCode 模型 | `accounts/models.py` | ✅ 已完成 |
| SMS 服务（Mock） | `accounts/sms.py` | ✅ 已完成（sandbox=True） |
| 发送验证码 API | `accounts/views.py` | ✅ 已完成 |
| 手机号注册 API | `accounts/views.py` | ✅ 已完成 |
| 手机号登录 API | `accounts/views.py` | ✅ 已完成 |
| 密码登录 API | `accounts/views.py` | ✅ 已完成 |
| 当前用户 API | `accounts/views.py` | ✅ 已完成 |
| 订阅开通 API | `subscriptions/views.py` | ✅ 已完成 |
| 邀请成员 API | `teams/views.py` | ✅ 已完成 |
| 租户管理 API | `tenants/` | ✅ 已完成 |
| 接口契约文档 | `INTERFACES.md` | ✅ 已完成 |

### 1.4 Sprint 3 前的技术债务项

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | SMS 生产配置 | 当前为 sandbox=True，生产环境需配置真实阿里云凭证 |
| P2 | 支付回调验收 | 支付宝/微信支付沙箱测试 |
| P2 | 跨域 Token 刷新 | Cookie 刷新逻辑在浏览器跨域场景验证 |
| P3 | 压测与性能基线 | 高并发场景验证 |

### 1.5 Account API 整体完成度

根据 ROADMAP.md：Account API 当前完成度 **70%**

| 功能 | 状态 |
|------|------|
| 手机号认证（注册/登录/发送验证码） | ✅ 已完成 |
| 订阅开通 | ✅ 已完成 |
| 租户创建 | ✅ 已完成 |
| 邀请成员 | ✅ 已完成 |
| SMS 生产配置 | ❌ 待完成 |
| 支付回调（支付宝/微信） | ❌ 待完成 |
| Token 刷新（跨域） | ❌ 待完成 |
| 高并发压测 | ❌ 待完成 |

---

## 二、Sprint 3 任务清单

### Task 1: SMS 生产配置与真实发送验证

**目标**: 将 SMS 服务从 Mock 模式切换为生产模式，支持真实短信发送

**任务**:
1. 阅读当前 `accounts/sms.py` 代码，确认 sandbox=True 配置位置
2. 更新 `accounts/sms.py`:
   - 添加生产模式判断逻辑（检查 ALIYUN_SMS_ACCESS_KEY 是否配置）
   - sandbox=True 时跳过真实发送，仅记录日志
   - sandbox=False 时调用真实阿里云 SMS API
3. 更新 `.env.example` 添加生产 SMS 配置项:
   - `ALIYUN_SMS_ACCESS_KEY`
   - `ALIYUN_SMS_ACCESS_SECRET`
   - `ALIYUN_SMS_SIGN_NAME`
   - `ALIYUN_SMS_TEMPLATE_CODE`
4. 更新 `README.md` 添加生产部署 SMS 配置说明
5. 添加生产 SMS 配置验证测试:
   - 新增 `tests/test_sms_production_config.py`
   - 验证配置完整性（必填字段存在）
   - 验证 Mock 模式不发起真实请求

**验收标准**: sandbox=False 时可真实发送短信（需阿里云沙箱或测试账号验证）

**预计工时**: 2-3 小时

---

### Task 2: 支付回调接口实现

**目标**: 实现支付宝/微信支付回调接口，完成订阅支付闭环

**任务**:
1. 新增支付回调视图 `payments/callbacks.py`:
   - `AlipayCallbackView` - 支付宝手机支付回调
   - `WechatPayCallbackView` - 微信支付回调
2. 实现回调签名验证:
   - 支付宝 RSA2 签名验证
   - 微信支付 HMAC-SHA256 签名验证
3. 实现支付状态更新逻辑:
   - 回调验证通过后更新 Subscription 状态为 paid
   - 处理重复回调（幂等性）
   - 记录支付日志
4. 新增支付回调序列化器 `payments/serializers.py`:
   - AlipayCallbackSerializer
   - WechatPayCallbackSerializer
5. 添加支付回调路由 `payments/urls.py`
6. 更新 `INTERFACES.md` 添加支付回调接口文档
7. 添加支付回调测试:
   - 新增 `tests/test_payment_callbacks.py`
   - 支付宝回调签名验证测试
   - 微信支付回调签名验证测试
   - 支付状态更新测试
   - 重复回调幂等性测试

**验收标准**: 支付回调可正确验证签名并更新订阅状态

**预计工时**: 4-5 小时

---

### Task 3: Token 刷新机制增强（跨域支持）

**目标**: 增强 Token 刷新机制，支持浏览器跨域场景

**任务**:
1. 阅读当前 `accounts/views.py` 中 Token 刷新实现
2. 实现基于 Cookie 的 Token 刷新:
   - 登录时设置 HttpOnly Refresh Token Cookie
   - 刷新时从 Cookie 读取 Refresh Token
   - 跨域场景支持（设置 SameSite=Lax）
3. 添加 Token 刷新视图 `POST /api/auth/token/refresh/`:
   - 支持 Header + Cookie 两种刷新方式
   - 返回新的 Access Token 和 Refresh Token
4. 实现 Token 撤回机制:
   - 添加 Token 黑名单（Redis 实现）
   - 登出时撤回 Refresh Token
5. 添加 Token 刷新测试:
   - 新增 `tests/test_token_refresh.py`
   - Cookie 刷新测试
   - 跨域刷新测试
   - Token 撤回测试

**验收标准**: 跨域场景下 Token 可正常刷新

**预计工时**: 3-4 小时

---

### Task 4: 安全基线回归测试

**目标**: 确保 Sprint 3 代码改动不破坏 Sprint 1-2 安全修复

**任务**:
1. 执行现有安全测试回归:
   ```bash
   cd account/fipai-account && ./venv/bin/python manage.py test tests/ -v 2
   ```
2. 验证:
   - 邀请接受身份校验仍然有效
   - 团队角色越权提权保护仍然有效
   - JWT Token Claims 仍然正确
   - 订阅状态机流转仍然符合预期

**预计工时**: 0.5 小时

---

## 三、文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `payments/callbacks.py` | 支付宝/微信支付回调视图 |
| `payments/serializers.py` | 支付回调序列化器 |
| `payments/urls.py` | 支付回调路由 |
| `payments/__init__.py` | payments 模块初始化 |
| `tests/test_sms_production_config.py` | SMS 生产配置验证测试 |
| `tests/test_payment_callbacks.py` | 支付回调测试 |
| `tests/test_token_refresh.py` | Token 刷新测试 |

### 修改文件

| 文件 | 修改原因 |
|------|----------|
| `accounts/sms.py` | 生产 SMS 配置支持 |
| `.env.example` | 添加 SMS 生产配置项 |
| `README.md` | 添加 SMS 生产配置说明 |
| `INTERFACES.md` | 添加支付回调接口文档 |
| `accounts/urls.py` | 添加 Token 刷新路由（Cookie 支持） |

### 不变更文件

以下模块已正常工作，无需修改：
- `accounts/models.py` - SMSCode 模型 ✅
- `accounts/views.py` - 认证 API ✅（Task 3 会添加新视图）
- `accounts/serializers.py` - 序列化器 ✅
- `subscriptions/views.py` - 订阅管理 ✅
- `subscriptions/models.py` - 订阅模型 ✅
- `teams/views.py` - 团队管理 ✅
- `teams/models.py` - 团队模型 ✅
- `tenants/views.py` - 租户管理 ✅
- `tenants/serializers.py` - 租户序列化器 ✅

---

## 四、预计工时

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| Day 1 | Task 1: SMS 生产配置 | 2-3 小时 |
| Day 1-2 | Task 2: 支付回调接口 | 4-5 小时 |
| Day 2-3 | Task 3: Token 刷新增强 | 3-4 小时 |
| Day 3 | Task 4: 安全回归测试 | 0.5 小时 |
| **总计** | **Sprint 3** | **9.5-12.5 小时** |

---

## 五、Sprint 3 验收标准

1. **SMS 配置**: `accounts/sms.py` 支持生产模式切换，`tests/test_sms_production_config.py` 通过
2. **支付回调**: `payments/callbacks.py` 实现支付宝/微信回调，`tests/test_payment_callbacks.py` 通过
3. **Token 刷新**: 跨域 Cookie 刷新机制实现，`tests/test_token_refresh.py` 通过
4. **回归**: 现有 `tests/` 下所有测试通过（49 tests + 新增测试）
5. **文档**: `INTERFACES.md` 和 `README.md` 更新支付回调和 SMS 生产配置说明

---

## 六、依赖与阻塞

- **Task 1 (SMS)**: 无外部阻塞，可独立完成
- **Task 2 (支付回调)**: 依赖 Task 1 完成（SMS 配置可能需要短信触发支付场景）
- **Task 3 (Token 刷新)**: 无外部阻塞，可独立完成
- **前置条件**: Sprint 2 所有测试通过（49 tests passed）

---

## 七、风险与备注

1. **支付回调测试**: 真实支付回调需要支付宝/微信沙箱账号才能完整测试
2. **跨域 Cookie**: 生产环境需要 nginx 配置支持 SameSite=Lax 和 Secure 标志
3. **Redis 依赖**: Token 黑名单机制依赖 Redis 连接
4. **SMS 生产测试**: 真实发送需要阿里云 SMS 测试签名和模板

---

## 八、技术债务后续项（不在 Sprint 3 范围）

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P2 | 压测与性能基线 | 高并发场景验证 |
| P3 | 支付退款接口 | 用户退款流程 |
| P3 | 发票申请接口 | 用户申请发票 |
| P3 | 多租户数据隔离验证 | 租户间数据隔离审计 |
