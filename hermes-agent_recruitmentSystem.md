你是一位资深 AI Agent 架构师兼全栈研发工程师，请基于当前项目 hermes-agent，实现一个面向 recruitmentSystem 系统的 AI 查询功能。

一、需求背景

当前 recruitmentSystem 系统的数据存储在 MySQL 中。现在需要基于 hermes-agent 开发一个 AI 查询能力，使用户可以通过自然语言查询 recruitmentSystem 系统中的业务数据。

示例：

1. 用户提问：
   当前正在招聘的岗位有哪些？

   模型期望返回：
   当前正在招聘的岗位有 AI算法工程师、高级Java工程师岗位。

2. 用户提问：
   列出最近一周我的考勤数据。

   模型期望返回：
   返回当前用户最近一周的考勤明细，包括日期、上班打卡时间、下班打卡时间、考勤状态、迟到/早退情况等。

二、核心目标

请在 hermes-agent 当前项目基础上，实现一个 recruitmentSystem 数据查询 Agent / Skill，使其具备以下能力：

1. 支持自然语言理解。
2. 支持识别用户查询意图。
3. 支持根据用户问题生成安全 SQL。
4. 支持连接 recruitmentSystem 的 MySQL 数据库。
5. 支持查询岗位招聘数据。
6. 支持查询当前用户的考勤数据。
7. 支持权限控制，用户只能查询自己有权限的数据。
8. 支持 SQL 安全校验，禁止危险 SQL。
9. 支持将查询结果转换为自然语言回答。
10. 支持可扩展，后续可以继续增加候选人、简历、面试、录用、部门、员工等查询能力。

三、请先分析当前项目

在开始开发前，请先阅读当前 hermes-agent 项目结构，重点分析：

1. 当前 Skill 的目录结构和加载机制。
2. 当前是否已有 SKILL.md 规范。
3. 当前是否已有 Tool / MCP / Function Calling 调用机制。
4. 当前是否已有数据库连接工具。
5. 当前是否已有 LLM 调用封装。
6. 当前是否已有 Agent Runtime、Skill Registry、Tool Registry。
7. 当前是否已有配置文件，例如 config、env、toml、yaml、json。
8. 当前是否已有权限上下文、用户上下文、session 上下文。
9. 当前测试框架和代码风格。

如果项目中已有类似模块，请优先复用；如果没有，请按照 hermes-agent 当前项目风格新增模块。不要脱离项目结构单独写一套不可运行的代码。

四、功能边界

本次优先实现 recruitmentSystem 的 AI 查询功能，不做数据写入功能。

允许：

1. SELECT 查询。
2. 查询岗位招聘信息。
3. 查询当前用户考勤数据。
4. 查询结果自然语言总结。
5. 查询结果表格化返回。
6. 多轮对话中复用上下文。

禁止：

1. INSERT。
2. UPDATE。
3. DELETE。
4. DROP。
5. ALTER。
6. TRUNCATE。
7. CREATE。
8. REPLACE。
9. 多语句 SQL。
10. 绕过权限查询其他人的考勤数据。
11. 绕过租户、组织、用户权限查询数据。

五、推荐实现形态

请优先以 hermes-agent 的 Skill 方式实现，新增一个 recruitmentSystem 查询 Skill。

建议 Skill 名称：

recruitment-system-query

建议目录：

skills/recruitment-system-query/

如果当前项目 Skill 目录命名不同，请以项目实际结构为准。

Skill 至少包含：

1. SKILL.md
2. 查询意图识别逻辑
3. MySQL 查询工具封装
4. SQL 生成上下文构建
5. SQL 安全校验
6. 查询结果格式化
7. 单元测试
8. 示例配置

六、SKILL.md 要求

请为该 Skill 编写标准 SKILL.md，至少包含以下内容：

1. Skill 名称：
   recruitment-system-query

2. Skill 描述：
   用于查询 recruitmentSystem 系统中的招聘岗位、考勤、候选人、面试等业务数据。本期优先支持岗位招聘查询和当前用户考勤查询。

3. 触发场景：
   当用户询问招聘岗位、正在招聘的职位、岗位列表、招聘状态、我的考勤、最近一周考勤、打卡记录等问题时触发。

4. 输入：
   - user_question：用户自然语言问题
   - user_id：当前登录用户 ID
   - tenant_id：租户 ID，可选
   - org_id：组织 ID，可选
   - session_id：会话 ID，可选
   - time_range：时间范围，可选

5. 输出：
   - answer：自然语言回答
   - sql：实际执行 SQL，可配置是否返回
   - data：结构化查询结果
   - intent：识别出的查询意图
   - safe：SQL 是否安全
   - error：错误信息，可选

6. 安全规则：
   - 只允许 SELECT
   - 必须限制 LIMIT
   - 考勤查询必须绑定当前 user_id
   - 禁止查询无权限用户的数据
   - 禁止执行多语句 SQL
   - 禁止危险关键字

七、业务意图识别

请实现 Intent Recognizer，至少支持以下意图：

1. 查询当前正在招聘的岗位

用户可能问法：

- 当前正在招聘的岗位有哪些？
- 现在有哪些岗位在招？
- 招聘中的职位有哪些？
- 公司现在招哪些岗位？
- 列出开放招聘的岗位。
- 有哪些岗位还在招聘？

意图名称：

recruiting_job_list

2. 查询岗位详情

用户可能问法：

- AI算法工程师这个岗位要求是什么？
- 高级Java工程师招聘要求有哪些？
- 某个岗位的职责是什么？
- 这个岗位薪资范围是多少？

意图名称：

recruiting_job_detail

3. 查询我的最近一周考勤

用户可能问法：

- 列出最近一周我的考勤数据。
- 查看我上周的考勤。
- 最近七天我的打卡情况。
- 我这周有没有迟到？
- 我的考勤异常有哪些？

意图名称：

my_attendance_recent_week

4. 查询我的指定时间范围考勤

用户可能问法：

- 查询我 5 月份的考勤。
- 查看我 2026-05-01 到 2026-05-10 的打卡记录。
- 查询我昨天的考勤。
- 我上个月迟到了几次？

意图名称：

my_attendance_by_time_range

无法识别时返回：

unknown_query_intent

并提示用户可以查询招聘岗位或我的考勤数据。

八、MySQL 数据库连接

请新增 recruitmentSystem MySQL 数据源配置。

配置项建议：

RECRUITMENT_DB_HOST
RECRUITMENT_DB_PORT
RECRUITMENT_DB_USERNAME
RECRUITMENT_DB_PASSWORD
RECRUITMENT_DB_DATABASE
RECRUITMENT_DB_MAX_OPEN_CONNS
RECRUITMENT_DB_MAX_IDLE_CONNS
RECRUITMENT_DB_CONN_MAX_LIFETIME
RECRUITMENT_DB_QUERY_TIMEOUT_SECONDS

如果当前项目使用 toml / yaml / json 配置文件，请按项目规范新增配置。

要求：

1. 不允许硬编码数据库账号密码。
2. 支持从环境变量读取配置。
3. 支持连接超时。
4. 支持查询超时。
5. 支持连接池。
6. 支持健康检查。
7. 数据库异常需要有明确错误日志。

九、数据库表适配要求

由于当前需求没有提供 recruitmentSystem 的真实表结构，请先按以下方式实现：

1. 优先从 MySQL information_schema 自动读取表结构、字段名、字段注释。
2. 支持通过配置文件手工补充业务表、字段说明和指标口径。
3. 如果实际表名与下面建议表名不同，请通过配置映射解决，不要写死。

建议支持以下逻辑表配置：

1. 招聘岗位表：recruitment_job

可能字段：

- id：岗位 ID
- tenant_id：租户 ID
- job_name：岗位名称
- job_code：岗位编码
- department_id：招聘部门 ID
- department_name：招聘部门名称
- job_status：岗位状态
- recruit_status：招聘状态
- headcount：招聘人数
- hired_count：已招聘人数
- job_requirement：岗位要求
- job_description：岗位职责
- salary_min：最低薪资
- salary_max：最高薪资
- create_time：创建时间
- update_time：更新时间
- is_deleted：是否删除

2. 考勤记录表：attendance_record

可能字段：

- id：考勤记录 ID
- tenant_id：租户 ID
- user_id：员工用户 ID
- employee_id：员工 ID
- employee_name：员工姓名
- attendance_date：考勤日期
- check_in_time：上班打卡时间
- check_out_time：下班打卡时间
- attendance_status：考勤状态
- late_minutes：迟到分钟数
- early_leave_minutes：早退分钟数
- work_hours：工作时长
- exception_reason：异常原因
- create_time：创建时间
- update_time：更新时间
- is_deleted：是否删除

请实现 TableMapping 配置，允许将实际表名、字段名映射到统一业务语义。

十、SQL 生成策略

本功能可以采用“两阶段 SQL 生成”方式：

第一阶段：规则模板优先

对高频问题使用固定 SQL 模板，保证准确性和安全性。

1. 查询正在招聘的岗位

逻辑：

- 查询招聘岗位表
- 过滤未删除数据
- 过滤招聘状态为正在招聘 / open / recruiting
- 按更新时间或创建时间倒序
- 限制 LIMIT

示例 SQL 逻辑：

SELECT
    job_name,
    department_name,
    headcount,
    hired_count,
    job_status,
    recruit_status
FROM recruitment_job
WHERE is_deleted = 0
  AND recruit_status IN ('recruiting', 'open', '正在招聘')
ORDER BY update_time DESC
LIMIT 50;

注意：
实际字段名和状态值必须通过配置映射，不能完全写死。

2. 查询最近一周我的考勤

逻辑：

- 查询考勤记录表
- 必须绑定当前 user_id
- 查询最近 7 天
- 按 attendance_date 升序或降序
- 限制 LIMIT

示例 SQL 逻辑：

SELECT
    attendance_date,
    check_in_time,
    check_out_time,
    attendance_status,
    late_minutes,
    early_leave_minutes,
    work_hours,
    exception_reason
FROM attendance_record
WHERE is_deleted = 0
  AND user_id = :current_user_id
  AND attendance_date >= :start_date
  AND attendance_date < :end_date
ORDER BY attendance_date DESC
LIMIT 20;

第二阶段：LLM 辅助生成 SQL

对非模板覆盖的问题，可以让 LLM 基于安全上下文生成 SQL，但必须经过 SQL Guard 校验。

LLM SQL 生成上下文必须包含：

1. 用户问题。
2. 当前用户 user_id。
3. 当前租户 tenant_id。
4. 可用表列表。
5. 可用字段列表。
6. 字段业务含义。
7. 表关系。
8. 权限规则。
9. SQL 约束。
10. 输出 SQL 格式要求。

十一、SQL Guard 安全校验

请实现 SQL Guard，所有 SQL 执行前必须通过校验。

规则如下：

1. 只允许 SELECT。
2. 禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE、REPLACE。
3. 禁止多语句。
4. 禁止 SQL 注释绕过。
5. 禁止访问未授权表。
6. 禁止访问未授权字段。
7. 查询考勤数据时，必须包含当前 user_id 条件。
8. 如果系统是多租户，必须包含 tenant_id 条件。
9. 必须自动追加或校验 LIMIT。
10. LIMIT 默认不超过 100。
11. 查询超时时间必须可配置。
12. SQL 校验失败时，不执行查询，并返回明确错误原因。

十二、权限控制要求

请实现最小权限原则。

1. 查询岗位数据：
   - 普通用户可以查询正在招聘岗位。
   - 如果查询岗位内部字段，例如薪资、预算、招聘负责人等，需要预留权限校验。
   - 本期可以先只开放岗位名称、部门、招聘人数、岗位状态等安全字段。

2. 查询考勤数据：
   - 普通用户只能查询自己的考勤。
   - 不允许通过自然语言查询其他人的考勤。
   - 如果用户问“张三最近一周考勤”，需要判断当前用户是否有 HR / 管理员权限。
   - 本期如果没有权限系统，默认只允许查询当前 user_id 的考勤。

3. 所有查询：
   - 必须记录 user_id、tenant_id、question、sql、执行耗时、结果数量。
   - SQL 日志中注意脱敏敏感字段。

十三、Agent 查询接口

请新增或复用当前项目中的 Agent 调用入口。

建议接口或方法：

POST /api/recruitment-system/ai-query

请求参数：

{
  "tenant_id": "t001",
  "user_id": "u001",
  "session_id": "s001",
  "question": "当前正在招聘的岗位有哪些"
}

返回格式：

{
  "success": true,
  "intent": "recruiting_job_list",
  "answer": "当前正在招聘的岗位有 AI算法工程师、高级Java工程师岗位。",
  "data": [
    {
      "job_name": "AI算法工程师",
      "department_name": "AI研发部",
      "headcount": 2,
      "hired_count": 0,
      "recruit_status": "正在招聘"
    }
  ],
  "sql": "可配置是否返回",
  "safe": true,
  "trace_id": "..."
}

考勤查询返回示例：

{
  "success": true,
  "intent": "my_attendance_recent_week",
  "answer": "最近一周你共有 5 条考勤记录，其中正常 4 天，迟到 1 天，无早退记录。",
  "data": [
    {
      "attendance_date": "2026-05-18",
      "check_in_time": "09:02:00",
      "check_out_time": "18:05:00",
      "attendance_status": "迟到",
      "late_minutes": 2,
      "early_leave_minutes": 0,
      "work_hours": 8.0
    }
  ],
  "safe": true,
  "trace_id": "..."
}

十四、结果解释要求

查询结果不要直接原样返回数据库字段，需要转换成用户能理解的自然语言。

1. 岗位查询

如果有数据：

当前正在招聘的岗位有 {岗位1}、{岗位2}、{岗位3}。其中 {岗位1} 所属部门为 {部门}，计划招聘 {人数} 人。

如果无数据：

当前未查询到正在招聘的岗位。

2. 考勤查询

需要总结：

- 查询时间范围
- 总考勤天数
- 正常天数
- 迟到次数
- 早退次数
- 缺卡次数
- 异常明细

示例：

最近一周你共有 5 条考勤记录，其中正常 4 天，迟到 1 天，无早退记录。迟到发生在 2026-05-18，上班打卡时间为 09:02，迟到 2 分钟。

十五、时间范围解析

请实现基础时间解析能力，至少支持：

1. 今天
2. 昨天
3. 最近一周
4. 最近七天
5. 本周
6. 上周
7. 本月
8. 上个月
9. 指定日期，例如 2026-05-18
10. 指定日期范围，例如 2026-05-01 到 2026-05-10

如果当前项目已有时间解析工具，请复用。

十六、日志与审计

请记录结构化日志，至少包括：

1. trace_id
2. tenant_id
3. user_id
4. question
5. intent
6. generated_sql
7. sql_safe_result
8. query_duration_ms
9. result_count
10. error_message
11. created_at

注意：
敏感数据需要脱敏。
数据库密码不能出现在日志中。

十七、异常处理

请处理以下异常：

1. 无法识别用户意图。
2. 数据库连接失败。
3. SQL 生成失败。
4. SQL Guard 校验失败。
5. 查询超时。
6. 查询结果为空。
7. 字段映射缺失。
8. 表不存在。
9. 权限不足。
10. LLM 调用失败。

异常返回示例：

{
  "success": false,
  "error_code": "SQL_GUARD_REJECTED",
  "message": "当前查询未通过安全校验：考勤查询必须限定当前用户。",
  "trace_id": "..."
}

十八、测试要求

请补充单元测试和集成测试，至少覆盖：

1. Intent Recognizer 能识别“当前正在招聘的岗位有哪些”。
2. Intent Recognizer 能识别“列出最近一周我的考勤数据”。
3. 时间解析器能解析最近一周。
4. 岗位查询 SQL 模板生成正确。
5. 考勤查询 SQL 模板必须包含 user_id。
6. SQL Guard 能拦截 DELETE。
7. SQL Guard 能拦截多语句。
8. SQL Guard 能拦截无 user_id 的考勤查询。
9. SQL Guard 能自动限制 LIMIT。
10. MySQL 查询工具支持 mock 测试。
11. 岗位查询结果能生成自然语言回答。
12. 考勤查询结果能生成统计总结。
13. 数据库异常时返回明确错误。
14. 空结果时返回友好提示。

十九、验收标准

实现完成后必须满足：

1. 可以通过自然语言查询当前正在招聘的岗位。
2. 可以通过自然语言查询当前用户最近一周考勤。
3. 所有 SQL 都经过 SQL Guard。
4. 考勤查询不能越权查询其他用户。
5. 数据库配置全部配置化，不允许硬编码。
6. 查询结果可以返回结构化 data 和自然语言 answer。
7. 查询失败时有明确错误信息。
8. 有必要的日志和 trace_id。
9. 有单元测试覆盖核心逻辑。
10. 不破坏 hermes-agent 现有功能。
11. 代码风格符合当前项目规范。
12. Skill 文档完整，可被后续维护人员理解和扩展。

二十、实现优先级

请按以下顺序开发：

P0：
1. 分析 hermes-agent 当前 Skill 机制。
2. 新增 recruitment-system-query Skill。
3. 新增 recruitmentSystem MySQL 配置。
4. 新增 Intent Recognizer。
5. 新增岗位查询 SQL 模板。
6. 新增考勤查询 SQL 模板。
7. 新增 SQL Guard。
8. 新增 MySQL Query Tool。
9. 新增结果格式化器。
10. 新增基础测试。

P1：
1. 新增 Agent API 入口。
2. 新增时间范围解析。
3. 新增字段映射配置。
4. 新增审计日志。
5. 新增权限预留接口。
6. 新增 LLM SQL 生成兜底能力。

P2：
1. 接入 MySQL information_schema 自动读取表结构。
2. 增加更多 recruitmentSystem 查询能力，例如候选人、简历、面试、录用。
3. 接入 Milvus 做表字段语义召回。
4. 支持复杂多轮问数。
5. 支持图表建议。
6. 支持管理员查询团队考勤，但必须经过权限校验。

二十一、最终请输出

实现完成后，请输出：

1. 新增 / 修改文件列表。
2. Skill 目录说明。
3. 配置项说明。
4. API 调用示例。
5. 支持的用户问题示例。
6. SQL Guard 规则说明。
7. 权限控制说明。
8. 测试用例执行结果。
9. 尚未完成但已预留的扩展点。
10. 运行和验证步骤。

请开始基于当前 hermes-agent 项目进行分析和实现。