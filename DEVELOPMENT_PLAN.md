# Agent-Account Sprint 1 开发计划

> 制定日期: 2026-08-17
> 负责人: Agent-Account

---

## 一、当前状态盘点

### 1.1 代码完整性

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| **SMSCode 模型** | `accounts/models.py` | ✅ 已完成 | 含 is_used/expires_at 字段 |
| **SMS 服务** | `accounts/sms.py` | ✅ 已完成 | Aliyun SMS 封装，Mock 模式可用 |
| **发送验证码 API** | `accounts/views.py` | ✅ 已完成 | `/api/auth/send-code/` |
| **手机号注册 API** | `accounts/views.py` | ✅ 已完成 | `/api/auth/register/phone/` |
| **手机号登录 API** | `accounts/views.py` | ✅ 已完成 | `/api/auth/login/phone/` |
| **密码登录 API** | `accounts/views.py` | ✅ 已完成 | `/api/auth/login/` |
| **当前用户 API** | `accounts/views.py` | ✅ 已完成 | `/api/auth/me/` |
| **订阅开通 API** | `subscriptions/views.py` | ✅ 已完成 | `/api/subscriptions/{id}/activate/` |
| **邀请成员 API** | `teams/views.py` | ✅ 已完成 | InvitationViewSet 含 accept/邀请逻辑 |
| **租户管理 API** | `tenants/` | ✅ 已完成 | 含成员列表、邀请路由 |

### 1.2 待确认问题（来自 Review 2026-07-07）

根据 `account/docs/review-2026-07-07-account.md`：

| 优先级 | 问题 | 状态 |
|--------|------|------|
| Critical | 邀请接受身份校验缺失 | 🟡 待验证（代码已有 email/phone 匹配检查） |
| Critical | 团队角色越权提权 | 🟡 待验证（代码已有 owner 保护） |
| Critical | 账号注册接口可用性 | ✅ 已实现 |
| Important | 接口契约对齐 | 🟡 部分需要核对 |
| Important | Token 刷新 Cookie 逻辑 | ✅ 已实现 |

### 1.3 Sprint 边界确认

根据 `ROADMAP.md`：

| Sprint | 目标 | 状态 |
|--------|------|------|
| Sprint 1 | 手机号认证（阿里云 SMS） | ✅ 核心功能已完成 |
| Sprint 2 | Portal 登录/注册页 | 由 Agent-Portal 负责 |
| Sprint 3 | 订阅开通 + 租户创建 + 邀请同事 | ✅ 核心功能已完成 |

**结论**: Account API 的 Sprint 1-3 核心功能已完成，但需要对照 `INTERFACES.md` 逐项核对契约合规性，并补充测试。

---

## 二、Sprint 1 剩余任务清单

### 2.1 契约核对与修复

对照 `INTERFACES.md` 逐条核对：

#### 认证接口

| 接口 | 契约路径 | 核对结果 | 修复 |
|------|----------|----------|------|
| 发送验证码 | `POST /api/auth/send-code/` | ✅ 路径一致 | 无需修改 |
| 手机号注册 | `POST /api/auth/register/phone/` | ✅ 路径一致 | 无需修改 |
| 手机号登录 | `POST /api/auth/login/phone/` | ✅ 路径一致 | 无需修改 |
| 密码登录 | `POST /api/auth/login/` | ✅ 路径一致 | 无需修改 |
| 当前用户 | `GET /api/auth/me/` | ✅ 路径一致 | 无需修改 |
| Token 刷新 | `POST /api/auth/token/refresh/` | ✅ 路径一致 | 无需修改 |

#### 订阅/租户接口

| 接口 | 契约路径 | 核对结果 | 修复 |
|------|----------|----------|------|
| 套餐列表 | `GET /api/subscriptions/plans/` | ✅ 路径一致 | 无需修改 |
| 订阅套餐 | `POST /api/subscriptions/` | ✅ 路径一致 | 无需修改 |
| 我的订阅 | `GET /api/subscriptions/` | ✅ 路径一致 | 无需修改 |
| 开通订阅 | `POST /api/subscriptions/{id}/activate/` | ✅ 路径一致 | 无需修改 |
| 取消订阅 | `POST /api/subscriptions/{id}/cancel/` | ✅ 路径一致 | 无需修改 |

#### 租户/团队接口

| 接口 | 契约路径 | 核对结果 | 修复 |
|------|----------|----------|------|
| 我的租户 | `GET /api/tenants/` | ✅ 路径一致 | 无需修改 |
| 创建租户 | `POST /api/tenants/` | ✅ 路径一致 | 无需修改 |
| 租户成员 | `GET /api/tenants/{id}/members/` | ✅ 路径一致 | 无需修改 |
| 邀请成员 | `POST /api/tenants/{id}/invite/` | ✅ 路径一致 | 无需修改 |
| 我的邀请 | `GET /api/teams/invitations/` | ✅ 路径一致（实际为 `/api/teams/invitations/`） | 无需修改 |
| 接受邀请 | `POST /api/teams/invitations/accept/` | ✅ 路径一致 | 无需修改 |

### 2.2 JWT Token 契约核对

`INTERFACES.md` 定义 JWT Payload:
```typescript
interface JWTPayload {
  user_id: string;
  tenant_id: string;
  product_scopes: string[];
  roles: string[];
  exp: number;
  iat: number;
}
```

**当前实现** (`accounts/views.py` `add_custom_token_claims`):
- ✅ `tenant_id` - 已实现
- ✅ `product_scopes` - 已实现（从 Subscription 获取）
- ✅ `roles` - 已实现（TeamMember.role）
- ✅ `exp/iat` - SimpleJWT 默认提供

### 2.3 安全审查修复

根据 `review-2026-07-07-account.md` 发现的 Critical 问题：

| # | 问题 | 修复措施 | 状态 |
|---|------|----------|------|
| 1 | 邀请接受时身份校验 | `InvitationViewSet.accept_invitation` 已有 email/phone 匹配检查 | 🟡 需写测试验证 |
| 2 | 团队角色越权提权 | `TeamMemberViewSet.update_role` 已有 owner 保护 | 🟡 需写测试验证 |
| 3 | 注册接口契约对齐 | 已按 INTERFACES.md 实现 | ✅ 已完成 |

### 2.4 测试补齐

| 测试文件 | 覆盖内容 | 状态 |
|----------|----------|------|
| `tests/test_review_2026_07_07_account.py` | Review 问题复现测试 | 🟡 存在（7 failed） |
| - | 契约测试（send-code/register/login/activate） | ❌ 缺失 |
| - | JWT Token claims 测试 | ❌ 缺失 |

---

## 三、Sprint 1 具体任务清单

### Task 1: Review 问题修复验证

**目标**: 验证并修复 Agent-AccountReviewer 发现的 3 个 Critical 问题

**任务**:
1. 阅读 `account/docs/review-2026-07-07-account.md` 了解具体问题
2. 阅读 `account/docs/test-report-2026-07-07-account-review-followup.md` 了解失败用例
3. 对照代码确认问题是否已修复
4. 如未修复，制定修复方案并实施
5. 执行回归测试确认修复有效

**验收标准**: `python manage.py test tests.test_review_2026_07_07_account -v 2` 全部通过

### Task 2: 接口契约合规测试

**目标**: 编写接口契约测试，确保 API 响应符合 `INTERFACES.md` 定义

**任务**:
1. 新增 `tests/test_interface_contract.py`
2. 测试以下接口契约：
   - `POST /api/auth/send-code/` - 请求/响应格式
   - `POST /api/auth/register/phone/` - JWT 返回格式
   - `POST /api/auth/login/phone/` - JWT 返回格式
   - `GET /api/auth/me/` - 响应字段完整性（tenant_id, subscriptions 等）
   - `POST /api/subscriptions/{id}/activate/` - 响应 tenant_id/tenant_name
   - `POST /api/teams/invitations/accept/` - 身份校验逻辑

**验收标准**: 新增测试全部通过

### Task 3: JWT Token Claims 验证测试

**目标**: 确保 JWT Token 包含正确的 claims

**任务**:
1. 新增 `tests/test_jwt_claims.py`
2. 测试注册/登录后 Token 包含:
   - `tenant_id`（用户所属租户）
   - `product_scopes`（订阅的产品列表）
   - `roles`（TeamMember 角色）

**验收标准**: Token 解码后 claims 正确

### Task 4: 文档同步

**目标**: 确保项目 README 反映当前实现状态

**任务**:
1. 检查 `account/fipai-account/README.md` 是否需要更新
2. 如有新增 API，端点列表需要同步
3. 补充 `INTERFACES.md` 中定义但未在 README 列出的端点

---

## 四、文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `tests/test_interface_contract.py` | 接口契约测试 |
| `tests/test_jwt_claims.py` | JWT Claims 验证测试 |
| `docs/sprint1-acceptance-2026-08-17.md` | Sprint 1 验收报告 |

### 修改文件（如有修复）

| 文件 | 修改原因 |
|------|----------|
| `accounts/views.py` | 若 review 问题需代码修复 |
| `teams/views.py` | 若邀请身份校验需加强 |
| `tests/test_review_2026_07_07_account.py` | 回归测试 |

### 不变更文件

以下模块已正常工作，无需修改：
- `accounts/models.py` - SMSCode 模型 ✅
- `accounts/sms.py` - 阿里云 SMS ✅
- `accounts/serializers.py` - 序列化器 ✅
- `subscriptions/views.py` - 订阅管理 ✅
- `teams/models.py` - 团队模型 ✅

---

## 五、预计完成时间

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| Day 1 | Task 1: Review 问题修复验证 | 2-3 小时 |
| Day 2 | Task 2: 接口契约测试编写 | 2-3 小时 |
| Day 3 | Task 3: JWT Claims 测试编写 | 1-2 小时 |
| Day 4 | Task 4: 文档同步 + 回归验证 | 1 小时 |
| **总计** | **Sprint 1 收尾** | **1-2 天** |

---

## 六、Sprint 1 验收标准

1. **Review 问题修复**: `tests/test_review_2026_07_07_account.py` 全部通过（或确认为 false positive）
2. **契约测试**: `tests/test_interface_contract.py` 全部通过
3. **JWT 测试**: `tests/test_jwt_claims.py` 全部通过
4. **回归**: 现有 `tests/` 下所有测试通过
5. **文档**: `README.md` 与当前实现一致

---

## 七、依赖与阻塞

- **无外部阻塞**: Sprint 1 任务可独立完成
- **依赖关系**: Sprint 2 (Portal) 依赖 Account API 契约正确性，确保 Task 2 优先完成

---

## 八、风险与备注

1. **SMS 真实发送**: 当前 `sms.py` 为 Mock 模式（sandbox=True），生产环境需配置真实的阿里云凭证
2. **数据库状态**: Review 测试可能依赖特定数据库状态（已有用户/订阅），测试环境需准备 fixture
3. **Token 刷新**: Cookie 刷新逻辑已实现，但需在浏览器环境下验证跨域场景
