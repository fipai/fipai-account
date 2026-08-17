# Agent-Account Sprint 2 开发计划

> 制定日期: 2026-08-17
> 负责人: Agent-Account

---

## 一、当前状态（Sprint 1 完成后）

### 1.1 Sprint 1 完成情况

根据 `DEVELOPMENT_PLAN.md` 和 ROADMAP.md 记录：

| 模块 | 状态 | 说明 |
|------|------|------|
| Sprint 1 Review 修复 | ✅ 已完成 | 6 个审查问题已全部修复 |
| 回归测试 | ✅ 已通过 | 11 tests passed |
| Sprint 1-3 核心功能 | ✅ 已完成 | 手机号认证、订阅开通、租户创建、邀请成员 |

### 1.2 Sprint 1 待办项（未完成）

根据 `DEVELOPMENT_PLAN.md` 原计划：

| 任务 | 状态 | 说明 |
|------|------|------|
| Task 4: 文档同步 | ❌ 未完成 | README.md 仍显示旧版邮箱注册流程 |

### 1.3 当前代码完整性

| 模块 | 文件 | 状态 |
|------|------|------|
| SMSCode 模型 | `accounts/models.py` | ✅ 已完成 |
| SMS 服务 | `accounts/sms.py` | ✅ 已完成（Mock 模式） |
| 发送验证码 API | `accounts/views.py` | ✅ 已完成 |
| 手机号注册 API | `accounts/views.py` | ✅ 已完成 |
| 手机号登录 API | `accounts/views.py` | ✅ 已完成 |
| 密码登录 API | `accounts/views.py` | ✅ 已完成 |
| 当前用户 API | `accounts/views.py` | ✅ 已完成 |
| 订阅开通 API | `subscriptions/views.py` | ✅ 已完成 |
| 邀请成员 API | `teams/views.py` | ✅ 已完成 |
| 租户管理 API | `tenants/` | ✅ 已完成 |
| Review 测试 | `tests/test_review_2026_07_07_account.py` | ✅ 7 passed |
| 安全测试 | `tests/test_settings_security.py` | ✅ 4 passed |

### 1.4 接口契约对照（INTERFACES.md）

| 接口 | 契约路径 | 状态 |
|------|----------|------|
| 发送验证码 | `POST /api/auth/send-code/` | ✅ 一致 |
| 手机号注册 | `POST /api/auth/register/phone/` | ✅ 一致 |
| 手机号登录 | `POST /api/auth/login/phone/` | ✅ 一致 |
| 密码登录 | `POST /api/auth/login/` | ✅ 一致 |
| 当前用户 | `GET /api/auth/me/` | ✅ 一致 |
| Token 刷新 | `POST /api/auth/token/refresh/` | ✅ 一致 |
| 套餐列表 | `GET /api/subscriptions/plans/` | ✅ 一致 |
| 订阅套餐 | `POST /api/subscriptions/` | ✅ 一致 |
| 我的订阅 | `GET /api/subscriptions/` | ✅ 一致 |
| 开通订阅 | `POST /api/subscriptions/{id}/activate/` | ✅ 一致 |
| 我的租户 | `GET /api/tenants/` | ✅ 一致 |
| 创建租户 | `POST /api/tenants/` | ✅ 一致 |
| 租户成员 | `GET /api/tenants/{id}/members/` | ✅ 一致 |
| 邀请成员 | `POST /api/tenants/{id}/invite/` | ✅ 一致 |
| 我的邀请 | `GET /api/teams/invitations/` | ✅ 一致 |
| 接受邀请 | `POST /api/teams/invitations/accept/` | ✅ 一致 |

### 1.5 技术债务项

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P2 | 文档更新 | README.md 显示旧版邮箱注册，需更新为手机号认证流程 |
| P2 | SMS 生产配置 | 当前为 sandbox=True，生产环境需配置真实阿里云凭证 |
| P3 | 支付回调验收 | 支付宝/微信支付沙箱测试 |
| P3 | 跨域 Token 刷新 | Cookie 刷新逻辑在浏览器跨域场景验证 |

---

## 二、Sprint 2 任务清单

### Task 1: 文档同步与更新

**目标**: 确保项目 README 反映当前 Sprint 1-3 实现状态

**任务**:
1. 阅读当前 `README.md` 内容
2. 对比 `DEVELOPMENT_PLAN.md` 和 `INTERFACES.md` 确认已实现的 API
3. 更新 README.md:
   - 移除邮箱验证注册流程（已替换为手机号认证）
   - 添加手机号注册/登录说明
   - 更新 API 端点列表，对齐 `INTERFACES.md`
   - 添加 SMS 配置说明（Mock vs 生产）
   - 添加订阅开通与租户创建说明

**验收标准**: README.md 与当前实现完全一致

**预计工时**: 1-2 小时

---

### Task 2: API 端点完整性测试

**目标**: 编写端到端契约测试，覆盖所有 INTERFACES.md 定义接口

**任务**:
1. 新增 `tests/test_full_contract_e2e.py`
2. 测试场景（完整用户旅程）:
   - 发送验证码 → 手机号注册 → 获取当前用户
   - 发送验证码 → 手机号登录 → 获取当前用户
   - 订阅套餐 → 开通订阅 → 创建租户
   - 邀请成员 → 接受邀请 → 验证成员列表
3. 测试以下接口:
   - `POST /api/auth/send-code/` - 验证请求格式
   - `POST /api/auth/register/phone/` - 验证 JWT 返回
   - `POST /api/auth/login/phone/` - 验证 JWT 返回
   - `GET /api/auth/me/` - 验证响应字段完整性（phone, name, tenant_id, subscriptions）
   - `POST /api/subscriptions/` - 订阅套餐
   - `POST /api/subscriptions/{id}/activate/` - 开通订阅
   - `POST /api/tenants/` - 创建租户
   - `POST /api/tenants/{id}/invite/` - 邀请成员
   - `POST /api/teams/invitations/accept/` - 接受邀请

**验收标准**: 所有 e2e 测试通过

**预计工时**: 2-3 小时

---

### Task 3: JWT Token Claims 验证测试

**目标**: 确保 JWT Token 包含正确的 claims（user_id, tenant_id, product_scopes, roles）

**任务**:
1. 新增 `tests/test_jwt_claims.py`
2. 测试用例:
   - 手机号注册后 Token 包含正确 user_id
   - 开通订阅后 Token 包含 tenant_id 和 product_scopes
   - 团队成员 Token 包含正确 roles
   - Token 过期时间合理（exp - iat = 1 hour）

**验收标准**: Token 解码后 claims 正确

**预计工时**: 1-2 小时

---

### Task 4: 订阅状态机契约测试

**目标**: 验证订阅状态流转符合业务规则

**任务**:
1. 新增 `tests/test_subscription_state_machine.py`
2. 测试用例:
   - 订阅创建后状态为 pending
   - 支付完成后状态为 paid/active
   - 开通必须要求 pending 状态（回归验证）
   - 重复开通返回错误
   - 取消订阅后状态变更

**验收标准**: 状态机测试全部通过

**预计工时**: 1-2 小时

---

### Task 5: 安全基线回归测试

**目标**: 确保 Sprint 2 代码改动不破坏 Sprint 1 安全修复

**任务**:
1. 执行现有安全测试回归:
   ```bash
   ./venv/bin/python manage.py test tests.test_settings_security tests.test_review_2026_07_07_account -v 2
   ```
2. 验证:
   - 邀请接受身份校验仍然有效
   - 团队角色越权提权保护仍然有效
   - 邮箱注册不再 500
   - 租户创建自动建立 owner membership

**预计工时**: 0.5 小时

---

## 三、文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `tests/test_full_contract_e2e.py` | 端到端契约测试 |
| `tests/test_jwt_claims.py` | JWT Token Claims 验证测试 |
| `tests/test_subscription_state_machine.py` | 订阅状态机契约测试 |

### 修改文件

| 文件 | 修改原因 |
|------|----------|
| `README.md` | 文档同步，更新为手机号认证流程 |

### 不变更文件

以下模块已正常工作，无需修改：
- `accounts/models.py` - SMSCode 模型 ✅
- `accounts/sms.py` - 阿里云 SMS ✅
- `accounts/views.py` - 认证 API ✅
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
| Day 1 | Task 1: 文档同步 | 1-2 小时 |
| Day 1 | Task 2: API 端点完整性测试 | 2-3 小时 |
| Day 2 | Task 3: JWT Claims 测试 | 1-2 小时 |
| Day 2 | Task 4: 订阅状态机测试 | 1-2 小时 |
| Day 2 | Task 5: 安全回归测试 | 0.5 小时 |
| **总计** | **Sprint 2** | **6-9 小时** |

---

## 五、Sprint 2 验收标准

1. **文档**: `README.md` 与当前实现一致
2. **契约测试**: `tests/test_full_contract_e2e.py` 全部通过
3. **JWT 测试**: `tests/test_jwt_claims.py` 全部通过
4. **状态机测试**: `tests/test_subscription_state_machine.py` 全部通过
5. **回归**: 现有 `tests/` 下所有测试通过（11 tests）
6. **覆盖率**: 核心 API 路径测试覆盖

---

## 六、依赖与阻塞

- **无外部阻塞**: Sprint 2 任务可独立完成
- **前置条件**: Sprint 1 Review 问题已全部修复并验证通过

---

## 七、风险与备注

1. **SMS 生产配置**: 当前 `sms.py` 为 Mock 模式（sandbox=True），生产环境需配置真实的阿里云凭证
2. **支付回调**: 沙箱环境测试需要支付宝/微信沙箱账号
3. **跨域 Token 刷新**: Cookie 刷新逻辑在浏览器跨域场景下需要 nginx 配合配置
4. **数据库状态**: e2e 测试依赖干净的数据库状态，使用 Django transaction 隔离

---

## 八、技术债务后续项（不在 Sprint 2 范围）

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P2 | 支付回调 e2e 测试 | 支付宝/微信支付真实回调测试 |
| P2 | nginx 配置更新 | 跨域 Cookie 配置 |
| P3 | 阿里云 SMS 生产验证 | 真实发送测试 |
| P3 | 压测与性能基线 | 高并发场景验证 |
