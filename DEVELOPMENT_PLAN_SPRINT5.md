# Agent-Account Sprint 5 开发计划

> 制定日期: 2026-08-17
> 负责人: Agent-Account

---

## 一、当前状态（Sprint 4 完成后）

### 1.1 Sprint 4 完成情况

根据 `DEVELOPMENT_PLAN_SPRINT4.md` 和 ROADMAP.md 记录：

| 模块 | 状态 | 说明 |
|------|------|------|
| Task 1: 压测与性能基线 | ✅ 已完成 | `locustfile.py` + `tests/test_performance_baseline.py` (6 tests) |
| Task 2: 支付退款接口 | ✅ 已完成 | `payments/` 退款 API + `tests/test_refund_api.py` (18 tests) |
| Task 3: 发票申请接口 | ✅ 已完成 | `invoices/` 发票 API + `tests/test_invoice_api.py` (13 tests) |
| Task 4: 多租户数据隔离验证 | ✅ 已完成 | `tests/test_tenant_isolation_account.py` (25 tests) |
| Task 5: 安全基线回归测试 | ✅ 已通过 | 117 tests total passed |

### 1.2 Sprint 4 测试汇总

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
- tests/test_refund_api.py: 18 passed (Sprint 4 新增)
- tests/test_invoice_api.py: 13 passed (Sprint 4 新增)
- tests/test_tenant_isolation_account.py: 25 passed (Sprint 4 新增)
- tests/test_performance_baseline.py: 6 passed (Sprint 4 新增)
Total: 117 passed
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
| 退款申请 API | `payments/` | ✅ 已完成 |
| 发票申请 API | `invoices/` | ✅ 已完成 |
| Token 刷新（Cookie 跨域） | `accounts/views.py` | ✅ 已完成 |
| 租户隔离验证 | `tests/test_tenant_isolation_account.py` | ✅ 已完成 |
| 性能基线测试 | `tests/test_performance_baseline.py` | ✅ 已完成 |
| 接口契约文档 | `INTERFACES.md` | ✅ 已完成 |

### 1.4 Sprint 4 前的技术债务项

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | 账户安全增强（2FA） | 二次认证增强账户安全 |
| P2 | 账户注销/删除功能 | GDPR 合规，用户数据删除权 |
| P2 | 发票 PDF 电子化 | 替代纸质发票 |
| P2 | 审计日志完善 | 记录关键操作日志 |
| P3 | 管理员后台 | 租户管理、用户管理 |

### 1.5 Account API 整体完成度

根据 ROADMAP.md：Account API 当前完成度 **95%**

| 功能 | 状态 |
|------|------|
| 手机号认证（注册/登录/发送验证码） | ✅ 已完成 |
| 订阅开通 | ✅ 已完成 |
| 租户创建 | ✅ 已完成 |
| 邀请成员 | ✅ 已完成 |
| SMS 生产配置 | ✅ 已完成 |
| 支付回调（支付宝/微信） | ✅ 已完成 |
| Token 刷新（跨域） | ✅ 已完成 |
| 压测与性能基线 | ✅ 已完成 |
| 支付退款接口 | ✅ 已完成 |
| 发票申请接口 | ✅ 已完成 |
| 多租户数据隔离验证 | ✅ 已完成 |
| 2FA 二次认证 | ❌ 待完成 |
| 账户注销/删除 | ❌ 待完成 |
| 发票 PDF 电子化 | ❌ 待完成 |
| 审计日志完善 | ❌ 待完成 |
| 管理员后台 | ❌ 待完成 |

---

## 二、Sprint 5 任务清单

### Task 1: 账户安全增强（2FA）

**目标**: 实现二次认证功能，增强账户安全性

**任务**:
1. 阅读当前认证流程（`accounts/views.py`）
2. 新增 2FA 模型 `accounts/models.py`:
   - `TwoFactorAuth` 模型（user, enabled, method, secret, backup_codes, created_at）
3. 新增 2FA API `accounts/views.py`:
   - `POST /api/auth/2fa/setup/` — 启用 2FA（生成 TOTP secret）
   - `POST /api/auth/2fa/verify/` — 验证 2FA 代码
   - `POST /api/auth/2fa/disable/` — 禁用 2FA
   - `GET /api/auth/2fa/status/` — 查询 2FA 状态
4. 实现 TOTP 认证逻辑（基于 pyotp 或 similar library）
5. 添加 2FA 测试:
   - 新增 `tests/test_two_factor_auth.py`
   - 2FA 启用/验证/禁用测试
   - 备份码使用测试
6. 更新 `INTERFACES.md` 添加 2FA 接口文档
7. 更新 `README.md` 添加 2FA 说明

**验收标准**: 用户可启用 2FA，登录时需输入 TOTP 代码

**预计工时**: 3-4 小时

---

### Task 2: 账户注销/删除功能

**目标**: 实现用户账户注销功能，支持 GDPR 合规

**任务**:
1. 新增账户注销模型 `accounts/models.py`:
   - `AccountDeletionRequest` 模型（user, reason, status, requested_at, processed_at, processed_by）
2. 新增账户注销 API `accounts/views.py`:
   - `POST /api/account/request-deletion/` — 用户提交注销申请
   - `GET /api/account/deletion-status/` — 查询注销状态
   - `DELETE /api/account/` — 确认注销（需验证密码）
3. 实现软删除逻辑:
   - 用户数据匿名化处理（保留统计数据）
   - 保留租户和订阅记录（便于审计）
   - 发送注销确认邮件
4. 添加账户注销测试:
   - 新增 `tests/test_account_deletion.py`
   - 注销申请成功测试
   - 重复注销拒绝测试
   - 注销后数据匿名化验证
5. 更新 `INTERFACES.md` 添加注销接口文档

**验收标准**: 用户可提交注销申请，数据可正确匿名化

**预计工时**: 2-3 小时

---

### Task 3: 发票 PDF 电子化

**目标**: 实现发票 PDF 生成功能，替代纸质发票

**任务**:
1. 添加 PDF 生成依赖（reportlab 或 weasyprint）
2. 新增 PDF 生成服务 `invoices/pdf.py`:
   - `generate_invoice_pdf()` 生成发票 PDF
   - 包含：发票号、日期、购买方信息、销售方信息、商品明细、金额
3. 修改发票 API `invoices/views.py`:
   - 新增 `GET /api/invoices/{id}/pdf/` — 下载发票 PDF
4. 修改发票模型 `invoices/models.py`:
   - `InvoiceRequest` 添加 `pdf_url` 字段
5. 添加发票 PDF 测试:
   - 修改 `tests/test_invoice_api.py`
   - 添加 PDF 生成测试
6. 更新 `INTERFACES.md` 添加发票 PDF 下载接口

**验收标准**: 可生成并下载发票 PDF

**预计工时**: 2-3 小时

---

### Task 4: 审计日志完善

**目标**: 记录关键操作日志，支持管理员审计

**任务**:
1. 新增审计日志模型 `audit/models.py`:
   - `AuditLog` 模型（tenant_id, user_id, action, resource_type, resource_id, details, ip_address, user_agent, created_at）
2. 新增审计日志 API `audit/views.py`:
   - `GET /api/audit/logs/` — 查询审计日志（分页）
   - `GET /api/audit/logs/{id}/` — 日志详情
3. 实现审计日志中间件/装饰器:
   - 自动记录关键操作（登录、登出、订阅变更、权限变更）
4. 添加审计日志测试:
   - 新增 `tests/test_audit_logs.py`
   - 日志记录测试
   - 分页查询测试
   - 租户隔离测试
5. 更新 `INTERFACES.md` 添加审计日志接口

**验收标准**: 关键操作可生成审计日志并查询

**预计工时**: 2-3 小时

---

### Task 5: 安全基线回归测试

**目标**: 确保 Sprint 5 代码改动不破坏 Sprint 1-4 安全修复

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
   - 租户隔离仍然有效

**预计工时**: 0.5 小时

---

## 三、文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `accounts/2fa.py` | 2FA TOTP 服务 |
| `audit/__init__.py` | audit 模块初始化 |
| `audit/models.py` | AuditLog 模型 |
| `audit/views.py` | 审计日志视图 |
| `audit/serializers.py` | 审计日志序列化器 |
| `audit/urls.py` | 审计日志路由 |
| `invoices/pdf.py` | 发票 PDF 生成服务 |
| `tests/test_two_factor_auth.py` | 2FA API 测试 |
| `tests/test_account_deletion.py` | 账户注销测试 |
| `tests/test_audit_logs.py` | 审计日志测试 |

### 修改文件

| 文件 | 修改原因 |
|------|----------|
| `accounts/models.py` | 添加 TwoFactorAuth、AccountDeletionRequest 模型 |
| `accounts/views.py` | 添加 2FA、账户注销视图 |
| `accounts/urls.py` | 添加 2FA、账户注销路由 |
| `invoices/models.py` | 添加 pdf_url 字段 |
| `invoices/views.py` | 添加 PDF 下载视图 |
| `invoices/urls.py` | 添加 PDF 下载路由 |
| `tests/test_invoice_api.py` | 添加 PDF 测试 |
| `README.md` | 添加 2FA、账户注销、发票 PDF 说明 |
| `INTERFACES.md` | 添加 2FA、账户注销、审计日志、发票 PDF 接口文档 |

### 不变更文件

以下模块已正常工作，无需修改：
- `accounts/sms.py` - SMS 服务 ✅
- `accounts/serializers.py` - 序列化器 ✅
- `subscriptions/views.py` - 订阅管理 ✅
- `subscriptions/models.py` - 订阅模型 ✅
- `teams/views.py` - 团队管理 ✅
- `teams/models.py` - 团队模型 ✅
- `tenants/views.py` - 租户管理 ✅
- `tenants/serializers.py` - 租户序列化器 ✅
- `payments/views.py` - 支付回调 ✅
- `payments/models.py` - 支付模型 ✅

---

## 四、预计工时

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| Day 1 | Task 1: 2FA 二次认证 | 3-4 小时 |
| Day 2 | Task 2: 账户注销/删除 | 2-3 小时 |
| Day 2-3 | Task 3: 发票 PDF 电子化 | 2-3 小时 |
| Day 3 | Task 4: 审计日志完善 | 2-3 小时 |
| Day 4 | Task 5: 安全回归测试 | 0.5 小时 |
| **总计** | **Sprint 5** | **9.5-13.5 小时** |

---

## 五、Sprint 5 验收标准

1. **2FA**: `accounts/2fa.py` 实现，TOTP 验证通过，`tests/test_two_factor_auth.py` 通过
2. **账户注销**: 注销申请可提交，数据匿名化正确，`tests/test_account_deletion.py` 通过
3. **发票 PDF**: PDF 可生成并下载，`tests/test_invoice_api.py`（PDF 部分）通过
4. **审计日志**: 关键操作生成日志，`tests/test_audit_logs.py` 通过
5. **回归**: 现有 `tests/` 下所有测试通过（117 tests + 新增测试）
6. **文档**: `INTERFACES.md` 和 `README.md` 更新 2FA、注销、审计日志、发票 PDF 接口说明

---

## 六、依赖与阻塞

- **Task 1 (2FA)**: 无外部阻塞，可独立完成
- **Task 2 (注销)**: 依赖 Task 1 无直接依赖，可并行开发
- **Task 3 (发票PDF)**: 依赖 Task 2, 3 无直接依赖，可并行开发
- **Task 4 (审计日志)**: 依赖 Task 1, 2, 3 无直接依赖，可并行开发
- **前置条件**: Sprint 4 所有测试通过（117 tests passed）

---

## 七、风险与备注

1. **2FA 安全**: TOTP secret 必须加密存储，备份码需安全存储
2. **注销合规**: 账户注销需符合 GDPR 等数据保护法规要求
3. **发票合规**: 电子发票需符合税务合规要求（当前为基础版本）
4. **审计性能**: 审计日志高频写入需考虑异步写入或批量处理

---

## 八、Sprint 5 完成后 Account API 完成度

| 功能 | 状态 |
|------|------|
| 手机号认证（注册/登录/发送验证码） | ✅ 已完成 |
| 订阅开通 | ✅ 已完成 |
| 租户创建 | ✅ 已完成 |
| 邀请成员 | ✅ 已完成 |
| SMS 生产配置 | ✅ 已完成 |
| 支付回调（支付宝/微信） | ✅ 已完成 |
| Token 刷新（跨域） | ✅ 已完成 |
| 压测与性能基线 | ✅ 已完成 |
| 支付退款接口 | ✅ 已完成 |
| 发票申请接口 | ✅ 已完成 |
| 多租户数据隔离验证 | ✅ 已完成 |
| 2FA 二次认证 | ✅ Sprint 5 完成 |
| 账户注销/删除 | ✅ Sprint 5 完成 |
| 发票 PDF 电子化 | ✅ Sprint 5 完成 |
| 审计日志完善 | ✅ Sprint 5 完成 |

**Sprint 5 完成后 Account API 预计完成度: 99%**

剩余 1% 为可选优化项（管理员后台、API 版本管理等）
