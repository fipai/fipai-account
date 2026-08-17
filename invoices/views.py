"""
Invoices API Views
"""
import logging
from django.db import models
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import InvoiceRequest
from .serializers import InvoiceRequestSerializer, InvoiceRequestCreateSerializer
from .pdf import generate_invoice_pdf
from subscriptions.models import Subscription
from teams.models import TeamMember

logger = logging.getLogger(__name__)


class InvoiceRequestViewSet(viewsets.ModelViewSet):
    """发票申请管理"""
    queryset = InvoiceRequest.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceRequestSerializer

    def get_queryset(self):
        """只返回当前用户所属租户的发票申请"""
        user = self.request.user

        # 获取用户所在的租户
        memberships = TeamMember.objects.filter(user=user, status='active')
        tenant_ids = memberships.values_list('tenant_id', flat=True)

        # 返回当前用户的发票申请 或 用户所在租户的发票申请
        return InvoiceRequest.objects.filter(
            models.Q(user=user) | models.Q(tenant_id__in=tenant_ids)
        ).distinct()

    def create(self, request, *args, **kwargs):
        """用户提交发票申请"""
        serializer = InvoiceRequestCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # 获取用户所在的租户
        memberships = TeamMember.objects.filter(user=request.user, status='active', role='owner')
        tenant = memberships.first().tenant if memberships.exists() else None

        # 关联订阅
        subscription = None
        if 'subscription_id' in data:
            try:
                subscription = Subscription.objects.get(id=data['subscription_id'])
            except Subscription.DoesNotExist:
                return Response({'error': '订阅不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 创建发票申请
        invoice = InvoiceRequest.objects.create(
            user=request.user,
            tenant=tenant,
            subscription=subscription,
            invoice_type=data['invoice_type'],
            title=data['title'],
            tax_id=data.get('tax_id', ''),
            amount=data['amount'],
            status='pending'
        )

        return Response(
            InvoiceRequestSerializer(invoice).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """查询发票状态"""
        invoice = self.get_object()
        return Response({
            'id': invoice.id,
            'status': invoice.status,
            'status_display': invoice.get_status_display(),
            'title': invoice.title,
            'amount': str(invoice.amount),
            'invoice_type': invoice.invoice_type,
            'invoice_type_display': invoice.get_invoice_type_display(),
            'invoice_no': invoice.invoice_no,
            'processed_at': invoice.processed_at,
            'process_note': invoice.process_note,
            'created_at': invoice.created_at,
        })

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        """下载发票 PDF"""
        invoice = self.get_object()

        if invoice.status not in ('approved', 'issued'):
            return Response(
                {'error': '发票未批准，无法下载 PDF'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            pdf_data = generate_invoice_pdf(invoice)
            response = HttpResponse(pdf_data, content_type='application/pdf')
            filename = f'invoice_{invoice.invoice_no or invoice.id}.pdf'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            logger.error(f'生成发票 PDF 失败: {e}')
            return Response(
                {'error': '生成 PDF 失败'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )