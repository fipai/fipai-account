# Agent-Account Sprint 4 开发计划

> 制定日期: 2026-08-17
> 负责人: Agent-Account

---

## 一、当前状态（Sprint 3 完成后）

### 1.1 Sprint 3 完成情况

根据 `DEVELOPMENT_PLAN_SPRINT3.md` 和 ROADMAP.md 记录：

| 模块 | 状态 | 说明 |
|------|------|------|
| Task 1: SMS 生产配置 | ✅ 已完成 | `tests/test_sms_production_config.py` (6 tests) |
| Task 2: 支付回调接口实现 | ✅ 已完成 | `tests/test_payment_callbacks.py` (12 tests) |
| Task 3: Token 刷新机制增强 | ✅ 已完成 | `tests/test_token_refresh.py` (7 tests) |
| Task 4: 安全基线回归测试 | ✅ 已通过 | 71 tests total passed |

### 1.2 Sprint 3 测试汇总

```
cd account/fipai-account && ./venv/bin/python manage.py test tests/ -v 2
- tests/test_review_2026_07_07_account.py: 7 passed
- tests/test_settings_security.py: 4 passed
- tests/test_full_contract_e2e.py: 21 passed
- tests/test_jwt_claims.py: 6 passed
- tests/test_subscription_state_machine.py: 11 passed
- tests/test_sms_production_config.py: 6 passed
- tests/test_payment_callbacks.py: 12 passed
- tests/test_token_refresh.py: 7 passed
Total: 71 passed
```

### 1.3 当前代码完整性

| 模块 | 文件 | 状态 |
|------|------|------|
| SMSCode 模型 | `accounts/models.py` | ✅ 已完成 |
| SMS 服务（Mock/生产） | `accounts/sms.py` | ✅ 已完成 |
| 发送验证码 API | `accounts/views.py` | ✅ 已完成 |
| 手机号注册 API | `accounts/views.py` | ✅ 已完成 |
| 手机号登录 API | `accounts/views.py` | ✅ 已完成 |
| 密码登录 API | `accounts/views.py` | ✅ 已完成 |
| 当前用户 API | `accounts/views.py` | ✅ 已完成 |
| 订阅开通 API | `subscriptions/views.py` | ✅ 已完成 |
| 邀请成员 API | `teams/views.py` | ✅ 已完成 |
| 租户管理 API | `tenants/` | ✅ 已完成 |
| 支付回调 API | `payments/` | ✅ 已完成 |
| Token 刷新（Cookie 跨域） | `accounts/views.py` | ✅ 已完成 |
| 接口契约文档 | `INTERFACES.md` | ✅ 已完成 |

### 1.4 Sprint 4 前的技术债务项

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | 压测与性能基线 | 高并发场景验证 |
| P2 | 支付退款接口 | 用户退款流程 |
| P2 | 发票申请接口 | 用户申请发票 |
| P3 | 多租户数据隔离审计 | 租户间数据隔离验证 |

### 1.5 Account API 整体完成度

根据 ROADMAP.md：Account API 当前完成度 **85%**

| 功能 | 状态 |
|------|------|
| 手机号认证（注册/登录/发送验证码） | ✅ 已完成 |
| 订阅开通 | ✅ 已完成 |
| 租户创建 | ✅ 已完成 |
| 邀请成员 | ✅ 已完成 |
| SMS 生产配置 | ✅ 已完成 |
| 支付回调（支付宝/微信） | ✅ 已完成 |
| Token 刷新（跨域） | ✅ 已完成 |
| 压测与性能基线 | ❌ 待完成 |
| 支付退款接口 | ❌ 待完成 |
| 发票申请接口 | ❌ 待完成 |
| 多租户数据隔离验证 | ❌ 待完成 |

---

## 二、Sprint 4 任务清单

### Task 1: 压测与性能基线

**目标**: 建立 Account API 性能基准，验证高并发场景下系统稳定性

**任务**:
1. 阅读当前 Django settings 配置，确认 Database/Redis 连接配置
2. 添加 `locustfile.py` 压力测试脚本:
   - `/api/auth/send-code/` 发送验证码场景
   - `/api/auth/login/phone/` 手机号登录场景
   - `/api/auth/me/` 当前用户查询场景
   - `/api/subscriptions/` 订阅列表查询场景
3. 配置 locust 使用 SQLite 内存数据库测试（隔离环境）
4. 执行基线压测并记录结果:
   - 并发用户: 10, 50, 100
   - 记录 RPS (Requests Per Second)、平均响应时间、错误率
5. 识别性能瓶颈（N+1 查询、缺失索引等）
6. 添加性能回归测试:
   - 新增 `tests/test_performance_baseline.py`
   - 关键接口响应时间断言（p95 < 500ms）
7. 更新 `README.md` 添加压测说明

**验收标准**: 100 并发用户下 API 错误率 < 1%，p95 响应时间 < 1s

**预计工时**: 3-4 小时

---

### Task 2: 支付退款接口实现

**目标**: 实现用户退款申请流程，完成支付闭环

**任务**:
1. 新增退款模型 `payments/models.py`:
   - `RefundRequest` 模型（status, reason, amount, transaction_id, created_at）
2. 新增退款 API `payments/views.py`:
   - `POST /api/payments/refunds/` — 用户提交退款申请
   - `GET /api/payments/refunds/{id}/` — 查询退款状态
   - `GET /api/payments/refunds/` — 退款列表（当前用户）
3. 实现退款状态机:
   - pending → approved/rejected → refunded
   - 只有 subscription owner 可申请退款
4. 添加退款序列化器 `payments/serializers.py`:
   - `RefundRequestSerializer`
   - `RefundRequestCreateSerializer`
5. 添加退款测试:
   - 新增 `tests/test_refund_api.py`
   - 退款申请成功测试
   - 重复退款拒绝测试
   - 权限校验测试（仅 owner 可申请）
6. 更新 `INTERFACES.md` 添加退款接口文档

**验收标准**: 退款申请可正确创建并查询状态

**预计工时**: 3-4 小时

---

### Task 3: 发票申请接口实现

**目标**: 实现用户发票申请功能

**任务**:
1. 新增发票模型 `invoices/models.py`:
   - `InvoiceRequest` 模型（status, invoice_type, title, tax_id, amount, tenant_id, created_at）
2. 新增发票 API `invoices/views.py`:
   - `POST /api/invoices/` — 用户提交发票申请
   - `GET /api/invoices/{id}/` — 查询发票状态
   - `GET /api/invoices/` — 发票列表（当前用户/租户）
3. 添加发票序列化器 `invoices/serializers.py`:
   - `InvoiceRequestSerializer`
   - `InvoiceRequestCreateSerializer`
4. 添加发票测试:
   - 新增 `tests/test_invoice_api.py`
   - 发票申请成功测试
   - 必填字段校验测试
   - 租户隔离测试
5. 更新 `INTERFACES.md` 添加发票接口文档
6. 更新 `README.md` 添加发票申请说明

**验收标准**: 发票申请可正确创建并查询

**预计工时**: 2-3 小时

---

### Task 4: 多租户数据隔离验证

**目标**: 验证租户间数据隔离是否完整，修复潜在越权漏洞

**任务**:
1. 阅读当前租户隔离实现（`tenants/views.py`, `teams/views.py` 等）
2. 新增租户隔离测试 `tests/test_tenant_isolation_account.py`:
   - 租户 A 无法查询租户 B 的订阅
   - 租户 A 无法查询租户 B 的团队成员
   - 租户 A 无法查询租户 B 的邀请记录
   - 租户 A 无法查询租户 B 的退款记录
   - 租户 A 无法查询租户 B 的发票记录
   - X-Tenant-Id 与 JWT tenant 不匹配时返回 403
3. 执行隔离测试并修复发现的漏洞
4. 添加租户隔离回归测试确保修复不回归

**验收标准**: 所有租户隔离测试通过，无越权访问

**预计工时**: 2-3 小时

---

### Task 5: 安全基线回归测试

**目标**: 确保 Sprint 4 代码改动不破坏 Sprint 1-3 安全修复

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
   - Token 刷新 Cookie 机制仍然有效

**预计工时**: 0.5 小时

---

## 三、文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `locustfile.py` | 压力测试脚本 |
| `payments/models.py` | RefundRequest 模型 |
| `payments/serializers.py` | 退款序列化器（补充） |
| `payments/urls.py` | 退款路由 |
| `payments/views.py` | 退款视图（补充） |
| `invoices/__init__.py` | invoices 模块初始化 |
| `invoices/models.py` | InvoiceRequest 模型 |
| `invoices/serializers.py` | 发票序列化器 |
| `invoices/urls.py` | 发票路由 |
| `invoices/views.py` | 发票视图 |
| `tests/test_refund_api.py` | 退款 API 测试 |
| `tests/test_invoice_api.py` | 发票 API 测试 |
| `tests/test_tenant_isolation_account.py` | Account 租户隔离测试 |
| `tests/test_performance_baseline.py` | 性能基线测试 |

### 修改文件

| 文件 | 修改原因 |
|------|----------|
| `payments/views.py` | 添加退款视图 |
| `payments/urls.py` | 添加退款路由 |
| `payments/serializers.py` | 添加退款序列化器 |
| `README.md` | 添加压测说明、发票申请说明 |
| `INTERFACES.md` | 添加退款接口、发票接口文档 |

### 不变更文件

以下模块已正常工作，无需修改：
- `accounts/models.py` - SMSCode 模型 ✅
- `accounts/views.py` - 认证 API ✅
- `accounts/serializers.py` - 序列化器 ✅
- `accounts/sms.py` - SMS 服务 ✅
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
| Day 1 | Task 1: 压测与性能基线 | 3-4 小时 |
| Day 1-2 | Task 2: 支付退款接口 | 3-4 小时 |
| Day 2-3 | Task 3: 发票申请接口 | 2-3 小时 |
| Day 3 | Task 4: 多租户数据隔离验证 | 2-3 小时 |
| Day 3-4 | Task 5: 安全回归测试 | 0.5 小时 |
| **总计** | **Sprint 4** | **10.5-14.5 小时** |

---

## 五、Sprint 4 验收标准

1. **性能基线**: `locustfile.py` 可执行，100 并发下 p95 < 1s，`tests/test_performance_baseline.py` 通过
2. **退款接口**: `payments/` 退款 API 实现，`tests/test_refund_api.py` 通过
3. **发票接口**: `invoices/` 发票 API 实现，`tests/test_invoice_api.py` 通过
4. **租户隔离**: `tests/test_tenant_isolation_account.py` 全部通过，无越权漏洞
5. **回归**: 现有 `tests/` 下所有测试通过（71 tests + 新增测试）
6. **文档**: `INTERFACES.md` 和 `README.md` 更新退款和发票接口说明

---

## 六、依赖与阻塞

- **Task 1 (压测)**: 无外部阻塞，可独立完成
- **Task 2 (退款)**: 依赖 Task 1 无直接依赖，可并行开发
- **Task 3 (发票)**: 依赖 Task 2 无直接依赖，可并行开发
- **Task 4 (隔离验证)**: 依赖 Task 2, 3 完成（退款/发票模型就位后可测）
- **前置条件**: Sprint 3 所有测试通过（71 tests passed）

---

## 七、风险与备注

1. **压测环境**: 压测需隔离环境，避免影响生产数据
2. **退款权限**: 退款涉及资金，需严格校验 owner 权限
3. **发票合规**: 发票申请需符合税务合规要求（当前为基础版本）
4. **租户隔离**: 隔离测试需覆盖所有数据访问路径

---

## 八、Sprint 4 完成后 Account API 完成度

| 功能 | 状态 |
|------|------|
| 手机号认证（注册/登录/发送验证码） | ✅ 已完成 |
| 订阅开通 | ✅ 已完成 |
| 租户创建 | ✅ 已完成 |
| 邀请成员 | ✅ 已完成 |
| SMS 生产配置 | ✅ 已完成 |
| 支付回调（支付宝/微信） | ✅ 已完成 |
| Token 刷新（跨域） | ✅ 已完成 |
| 压测与性能基线 | ✅ Sprint 4 完成 |
| 支付退款接口 | ✅ Sprint 4 完成 |
| 发票申请接口 | ✅ Sprint 4 完成 |
| 多租户数据隔离验证 | ✅ Sprint 4 完成 |

**Sprint 4 完成后 Account API 预计完成度: 95%**

剩余 5% 为可选优化项（高级退款流程、发票电子化等）
