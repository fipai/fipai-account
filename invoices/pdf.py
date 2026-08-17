"""
Invoice PDF Generation Service
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def generate_invoice_pdf(invoice):
    """
    生成发票 PDF

    Args:
        invoice: InvoiceRequest 实例

    Returns:
        bytes: PDF 数据
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )

    styles = getSampleStyleSheet()

    # 中文样式
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=1,  # 居中
        spaceAfter=20,
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=8,
    )

    elements = []

    # 标题
    elements.append(Paragraph('增值税发票', title_style))
    elements.append(Spacer(1, 10*mm))

    # 基本信息
    info_data = [
        ['发票号:', invoice.invoice_no or '待分配'],
        ['开票日期:', datetime.now().strftime('%Y年%m月%d日')],
        ['发票类型:', invoice.get_invoice_type_display()],
    ]

    info_table = Table(info_data, colWidths=[80*mm, 100*mm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 10*mm))

    # 购买方信息
    elements.append(Paragraph('<b>购买方信息</b>', normal_style))
    buyer_data = [
        ['购买方名称:', invoice.title],
        ['税号:', invoice.tax_id or 'N/A'],
    ]
    buyer_table = Table(buyer_data, colWidths=[80*mm, 100*mm])
    buyer_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(buyer_table)
    elements.append(Spacer(1, 10*mm))

    # 销售方信息
    elements.append(Paragraph('<b>销售方信息</b>', normal_style))
    seller_data = [
        ['销售方名称:', '飞谱智能科技（上海）有限公司'],
        ['税号:', '91310115MA1K4BXL3Q'],
        ['地址:', '上海市浦东新区张江高科技园区'],
        ['电话:', '400-123-4567'],
    ]
    seller_table = Table(seller_data, colWidths=[80*mm, 100*mm])
    seller_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(seller_table)
    elements.append(Spacer(1, 10*mm))

    # 商品明细
    elements.append(Paragraph('<b>商品明细</b>', normal_style))

    # 获取订阅信息
    plan_name = ''
    amount = invoice.amount
    if invoice.subscription and invoice.subscription.plan:
        plan_name = invoice.subscription.plan.name

    items_data = [
        ['序号', '商品名称', '规格', '数量', '单价', '金额'],
        ['1', plan_name or '订阅服务', '-', '1', f'{amount}', f'{amount}'],
    ]

    items_table = Table(items_data, colWidths=[30*mm, 60*mm, 30*mm, 25*mm, 35*mm, 35*mm])
    items_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 10*mm))

    # 金额汇总
    total_data = [
        ['合计金额:', f'¥{amount}'],
        ['税率:', '6%'],
        ['税额:', f'¥{float(amount) * 0.06:.2f}'],
        ['价税合计:', f'¥{float(amount) * 1.06:.2f}'],
    ]

    total_table = Table(total_data, colWidths=[150*mm, 50*mm])
    total_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 20*mm))

    # 备注
    elements.append(Paragraph('<b>备注:</b> 本发票由系统自动开具，如有问题请联系客服', normal_style))

    # 构建 PDF
    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()

    return pdf_data
