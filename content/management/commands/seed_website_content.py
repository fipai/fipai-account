from django.core.management.base import BaseCommand
from django.utils import timezone

from content.models import BlogPost, CaseStudy, DocItem, PublicationStatus


BLOGS = [
    {
        'slug': 'semantic-api-practice',
        'title': '柯西数据平台语义接口实战：让 AI 真正理解企业数据',
        'title_en': 'Semantic API in practice: helping AI understand enterprise data',
        'excerpt': '从数据语义、关系和质量标签出发，构建面向 AI 的可信数据接口。',
        'excerpt_en': 'Build a trustworthy AI-ready data interface with semantics, relationships and quality labels.',
        'category': '实践指南', 'category_en': 'Practical guide',
        'tags': ['教程', '数据语义', '人工智能'], 'tags_en': ['Guide', 'Data semantics', 'AI'],
        'content': '# 为什么需要语义接口\n\n企业数据分散在多个系统中，字段名称、口径和业务关系往往只有业务团队真正了解。语义接口把这些上下文变成 AI 可以理解、调用和验证的能力。\n\n## 实施路径\n\n1. 统一业务对象和指标口径。\n2. 为数据资产补充质量与来源标签。\n3. 通过自然语言和结构化接口提供查询。\n4. 用真实业务结果持续校正语义。\n\n## 结果\n\n业务人员可以更快获得可信答案，AI 也能在明确上下文中完成分析。',
        'content_en': '# Why semantic APIs matter\n\nEnterprise data is spread across systems. A semantic API turns business context, quality and relationships into capabilities that AI can understand and verify.\n\n## A practical path\n\n1. Define shared business objects and metrics.\n2. Add quality and lineage labels.\n3. Expose natural-language and structured queries.\n4. Improve semantics with real outcomes.\n\nThe result is faster, more trustworthy business analysis.',
        'author': '飞谱智能技术团队', 'author_en': 'FIP.AI engineering team',
    },
    {
        'slug': 'agenticorcha-automation-practice',
        'title': '奥察智能体平台：从单点助手到业务自动化协作',
        'title_en': 'From assistants to coordinated business automation',
        'excerpt': '如何让多个智能体围绕真实业务任务协同工作，并把结果交给人确认或系统执行。',
        'excerpt_en': 'How multiple agents can collaborate around real business tasks and hand results to people or systems.',
        'category': '最佳实践', 'category_en': 'Best practice',
        'tags': ['智能体', '自动化', '协作'], 'tags_en': ['Agents', 'Automation', 'Collaboration'],
        'content': '# 从回答问题到完成任务\n\n企业使用 AI 的价值不止是生成一段文字，而是让任务能够被拆解、执行、交接和验证。\n\n奥察智能体平台负责定义智能体、编排技能和管理执行结果；业务规则、审批和执行责任则交给业务系统和决策运营流程。',
        'content_en': '# From answering to completing work\n\nThe value of enterprise AI is not only text generation. Tasks need to be decomposed, executed, handed over and verified.\n\nAgenticOrcha defines agents, skills and execution; business rules, approvals and accountability stay in the business and decision layers.',
        'author': '飞谱智能产品团队', 'author_en': 'FIP.AI product team',
    },
    {
        'slug': 'decisionops-audit',
        'title': '智策运营大脑：让 AI 决策可审阅、可追溯、可改进',
        'title_en': 'Making AI decisions reviewable, traceable and improvable',
        'excerpt': '从证据链、人工审核到执行反馈，建立企业可以信任的决策闭环。',
        'excerpt_en': 'Build a decision loop enterprises can trust with evidence, human review and execution feedback.',
        'category': '产品解析', 'category_en': 'Product insight',
        'tags': ['决策', '审计', '人机协作'], 'tags_en': ['Decisioning', 'Audit', 'Human-AI collaboration'],
        'content': '# 为什么决策需要运营\n\nAI 可以快速提出方案，但企业还需要知道依据是什么、谁批准了方案、执行后效果如何。智策运营大脑把这些环节连接起来。\n\n每次决策都保留上下文、证据、审核动作和实际结果，让团队能够复盘并持续优化规则。',
        'content_en': '# Why decisions need operations\n\nAI can propose options quickly, but enterprises need the evidence, the approver and the outcome. DecisionOps connects those steps with traceable context, review actions and real results.',
        'author': '飞谱智能技术团队', 'author_en': 'FIP.AI engineering team',
    },
    {
        'slug': 'business-automation-blueprint',
        'title': '用 AI 让企业业务自动运行：从数据到执行的完整路径',
        'title_en': 'A blueprint for AI-powered business automation',
        'excerpt': '企业不需要再增加更多孤立工具，而需要把业务、数据、决策和执行连成一个闭环。',
        'excerpt_en': 'Enterprises need a connected loop across business, data, decisions and execution—not more isolated tools.',
        'category': '行业洞察', 'category_en': 'Industry insight',
        'tags': ['业务自动化', '企业 AI', '业务系统'], 'tags_en': ['Business automation', 'Enterprise AI', 'Business systems'],
        'content': '# 自动化的终点是业务闭环\n\n真正有效的企业 AI 系统，应当从业务问题出发，理解企业数据，调用智能体完成分析，在关键节点保留人的判断，并将批准后的动作下发到业务系统。\n\n这样，企业减少的是重复劳动，增加的是可持续的业务价值。',
        'content_en': '# The destination is a business loop\n\nAn effective enterprise AI system starts with a business problem, understands enterprise data, uses agents for analysis, keeps people in control of critical decisions and executes approved actions in business systems.\n\nThe outcome is less repetitive work and more sustainable value.',
        'author': '飞谱智能', 'author_en': 'FIP.AI',
    },
]


DOCS = [
    ('datacognis', [('semantic-api', '语义接口规范', '接口'), ('quickstart', '快速开始指南', '教程'), ('data-quality', '数据质量标签', '指南')]),
    ('agenticorcha', [('agent-guide', '智能体开发指南', '教程'), ('skills', '工具与技能开发', '开发'), ('multi-agent', '多智能体协作', '架构')]),
    ('decisionops', [('decision-api', '决策流 API 参考', '接口'), ('audit-guide', '决策审计指南', '指南'), ('human-loop', '人机协同最佳实践', '实践')]),
    ('bizgen', [('business-builder', '业务系统构建指南', '教程'), ('gateway', '业务网关集成', '集成'), ('execution', '自动化执行接口', '接口')]),
]

PRODUCT_NAMES = {
    'datacognis': ('柯西数据平台', 'DataCognis'),
    'agenticorcha': ('奥察智能体平台', 'AgenticOrcha'),
    'decisionops': ('智策运营大脑', 'DecisionOps'),
    'bizgen': ('必捷业务集成平台', 'BizGen'),
}


CASES = [
    ('retail-data', '某知名零售连锁', '零售连锁', '柯西数据平台帮助销售团队更快获得可信洞察', 'datacognis'),
    ('logistics-agents', '某头部物流企业', '物流运输', '奥察智能体平台协同处理复杂客户服务任务', 'agenticorcha'),
    ('finance-decisions', '某城商行', '金融银行', '智策运营大脑让审批更快，同时保留人工把关', 'decisionops'),
    ('manufacturing-automation', '某大型制造企业', '智能制造', '连接数据、分析和现场执行，减少非计划停机', 'datacognis'),
    ('business-operations', '某成长型制造企业', '业务运营', '必捷业务集成平台构建客户专属业务系统', 'bizgen'),
]


class Command(BaseCommand):
    help = 'Seed the initial published website content without overwriting existing records.'

    def handle(self, *args, **options):
        now = timezone.now()
        created = {'blogs': 0, 'docs': 0, 'cases': 0}
        for data in BLOGS:
            data = {**data, 'status': PublicationStatus.PUBLISHED, 'published_at': now}
            _, made = BlogPost.objects.get_or_create(slug=data['slug'], defaults=data)
            created['blogs'] += int(made)
        for product, items in DOCS:
            cn_name, en_name = PRODUCT_NAMES[product]
            for order, (slug, title, category) in enumerate(items, 1):
                data = {
                    'product': product, 'slug': slug, 'title': title, 'title_en': title,
                    'category': category, 'category_en': category, 'content': f'# {title}\n\n这是{cn_name}的初始文档。内容可由内容管理员继续完善。',
                    'content_en': f'# {title}\n\nThis is an initial document for {en_name}. Content editors can continue to refine it.',
                    'display_order': order, 'version': '1.0.0', 'status': PublicationStatus.PUBLISHED, 'published_at': now,
                }
                _, made = DocItem.objects.get_or_create(product=product, slug=slug, defaults=data)
                created['docs'] += int(made)
        for order, (slug, company, industry, description, product) in enumerate(CASES, 1):
            data = {
                'slug': slug, 'title': description, 'title_en': description, 'company': company, 'company_en': company,
                'industry': industry, 'industry_en': industry, 'description': description, 'description_en': description,
                'challenge': '业务流程分散在多个系统和人工表格中，信息传递慢，管理者难以及时掌握变化。',
                'challenge_en': 'Work was spread across systems and spreadsheets, slowing information flow and visibility.',
                'solution': f'围绕{PRODUCT_NAMES[product][0]}建立从数据、分析到业务执行的闭环，并在关键节点保留人工确认。',
                'solution_en': f'Build a loop from data and analysis to execution with {PRODUCT_NAMES[product][1]}, keeping human review at critical points.',
                'results': '减少重复录入，加快业务响应，让执行结果可以持续追踪。',
                'results_en': 'Less repetitive work, faster response and measurable execution outcomes.',
                'products': [product], 'status': PublicationStatus.PUBLISHED, 'published_at': now, 'featured': True,
                'case_type': 'demo', 'business_goal': '减少重复劳动，让关键业务流程自动运行', 'business_goal_en': 'Reduce repetitive work and automate the critical business loop',
                'company_size': '参考场景', 'business_tags': ['业务自动化', '人机协作'], 'display_order': order,
                'workflow_before': '信息分散在多个系统、表格和人工沟通中，业务人员需要反复核对和传递。',
                'workflow_before_en': 'Information was spread across systems, spreadsheets and manual communication.',
                'workflow_after': '系统汇总业务数据，AI 提出方案，负责人确认关键决策，批准后的动作自动执行并追踪结果。',
                'workflow_after_en': 'The system consolidates data, AI proposes options, people approve critical decisions, and approved actions are executed and tracked.',
                'automation_steps': ['自动汇总业务数据', '识别问题并生成方案', '人工确认关键决策', '下发执行并追踪结果'],
                'automation_steps_en': ['Consolidate business data', 'Identify issues and propose options', 'Review critical decisions', 'Execute and track outcomes'],
                'human_role': '业务负责人负责确认优先级、审批关键方案和处理例外情况。',
                'human_role_en': 'Business owners set priorities, approve critical options and handle exceptions.',
                'metrics': [{'label': '重复录入减少', 'value': '80%', 'source': '场景示例'}],
                'testimonial': '这是面向客户讨论的参考场景，正式上线前需要以客户实际数据校验结果。',
                'testimonial_en': 'This is a reference scenario; results should be validated with customer data before publication.',
                'testimonial_author': '飞谱智能参考场景',
            }
            case, made = CaseStudy.objects.get_or_create(slug=slug, defaults=data)
            if not made and not case.business_goal:
                for field, value in data.items():
                    if field not in {'slug', 'status', 'published_at'}:
                        setattr(case, field, value)
                case.save()
            created['cases'] += int(made)
        self.stdout.write(self.style.SUCCESS(f"Seeded website content: {created['blogs']} blogs, {created['docs']} docs, {created['cases']} cases."))
