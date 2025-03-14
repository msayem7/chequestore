# Standard library imports
import io
import json
from datetime import datetime
from decimal import Decimal

# Django imports
from django.http import HttpResponse
from django.db.models import Sum, Case, When, Q, F, DecimalField
from django.db import transaction
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404

# Django REST Framework imports
from rest_framework import viewsets, status
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cheques import serializers
from django.conf import settings

from rest_framework.decorators import api_view, permission_classes, action

from rest_framework_simplejwt.views import TokenObtainPairView

from django_filters import rest_framework as filters

# Third-party imports
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from openpyxl import Workbook

# Local imports
from .models import (
    Company, Branch, Customer, CreditInvoice,
    ChequeStore, InvoiceChequeMap, MasterClaim,
    CustomerClaim, ClaimCategory
)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_detail(request):
    serializer = serializers.UserSerializer(request.user)
    return Response(serializer.data)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = serializers.CustomTokenObtainPairSerializer


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = serializers.CompanySerializer

class BranchViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.BranchSerializer
    queryset = Branch.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = 'alias_id'

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            client_version = int(request.data.get('version'))
            instance = self.get_object()

            # Concurrency check
            if instance.version != client_version:
                return Response(
                    {'version': 'This branch has been modified by another user. Please refresh. current V, client_version v: ' + str(instance.version) + ' ' + str(client_version)},
                    status=status.HTTP_409_CONFLICT
                )

            # Increment version
            new_version = instance.version + 1

            # Partial update handling
            partial = kwargs.pop('partial', False)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)

            # Save with updated information
            serializer.save(updated_by=request.user, version=new_version)

            return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = serializers.CustomerSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'alias_id'
    filterset_fields = ['is_parent', 'parent']

    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = self.request.query_params.get('branch')
        
        print( 'self.request.query_params.get', self.request.query_params.get('is_active', 'true').lower())
           
        #if not self.request.user.is_staff:  # Example: admins see all
        if self.request.query_params.get('is_active'):
            is_active = self.request.query_params.get('is_active', 'true').lower() == 'true'
            print('is_active',is_active, 'self.request.query_params.get', self.request.query_params.get('is_active', 'true').lower())
            queryset = queryset.filter(is_active=is_active)
        
        # Filter by branch alias_id
        if branch_id:
            queryset = queryset.filter(branch__alias_id=branch_id)
            
        # Filter parent customers
        if self.request.query_params.get('is_parent'):
            is_parent = self.request.query_params.get('is_parent', 'true').lower() == 'true'
            queryset = queryset.filter(is_parent=is_parent)
        
        return queryset
    
    def update(self, request, *args, **kwargs):
        if (HasCustomerActivity.has_Activity(self, request)):
            return  Response({'error': 'Customer has active invoices or cheques. Inactivation is not possible'}, status=status.HTTP_409_CONFLICT)
        return super().update(request, *args, **kwargs)


class HasCustomerActivity(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = serializers.CustomerSerializer

    def has_Activity(self, request, *args, **kwargs):
        try:
            customer = get_object_or_404(Customer, alias_id=request.parser_context['kwargs']['alias_id'])
            has_activity = customer.creditinvoice_set.exists() or customer.chequestore_set.exists()
            return has_activity
        except Customer.DoesNotExist:
            return False
        
class CreditInvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.CreditInvoiceSerializer
    queryset = CreditInvoice.objects.all()
    lookup_field = 'alias_id'

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        if branch := params.get('branch'):
            queryset = queryset.filter(branch__alias_id=branch)
        if date_from := params.get('transaction_date_after'):
            queryset = queryset.filter(transaction_date__gte=date_from)
        if date_to := params.get('transaction_date_before'):
            queryset = queryset.filter(transaction_date__lte=date_to)
        if customer := params.get('customer'):
            queryset = queryset.filter(customer__alias_id=customer)
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):

        instance = self.get_object()
        if int(request.data.get('version')) != instance.version:
            return Response({'error': 'Version conflict'}, status=status.HTTP_409_CONFLICT)
        
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(
            instance, 
            data=request.data,  
            partial=partial
        )
        serializer.is_valid(raise_exception=True)
    #     if 'customer' in validated_data:
    #         validated_data['payment_grace_days'] = validated_data['customer'].grace_days 
        serializer.save(updated_by=request.user, version=instance.version + 1)
        
        return Response(serializer.data)


    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if latest := self.get_queryset().order_by('-updated_at').first():
            response.headers['Last-Modified'] = latest.updated_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response


class ChequeFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name='received_date', lookup_expr='gte')
    date_to = filters.DateFilter(field_name='received_date', lookup_expr='lte')
    status = filters.BaseInFilter(field_name='cheque_status', lookup_expr='in')

    class Meta:
        model = ChequeStore
        fields = ['customer', 'date_from', 'date_to', 'status']

        
class ChequeStoreViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.ChequeStoreSerializer
    queryset = ChequeStore.objects.all()
    lookup_field = 'alias_id'  
    lookup_url_kwarg = 'alias_id'  # Add this line (optional but explicit)
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ChequeFilter

    def get_queryset(self):
        queryset = ChequeStore.objects.filter(isActive=True)
        branch = self.request.query_params.get('branch')
        if branch:
            queryset = queryset.filter(branch__alias_id=branch)
        return queryset.order_by('-received_date')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if int(request.data.get('version')) != instance.version:
            return Response({'error': 'Version conflict'}, status=status.HTTP_409_CONFLICT)
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        instance = serializer.save()
        invoice_cheques = json.loads(self.request.data.get('invoice_cheques', '[]'))
        self._handle_invoice_cheques(instance, invoice_cheques)

    def perform_update(self, serializer):
        instance = serializer.save()
        invoice_cheques = json.loads(self.request.data.get('invoice_cheques', '[]'))
        instance.invoice_cheques.all().delete()
        self._handle_invoice_cheques(instance, invoice_cheques)
        
    def _handle_invoice_cheques(self, instance, invoice_cheques):
        for item in invoice_cheques:
            try:
                # Get CreditInvoice instance by alias_id
                credit_invoice = CreditInvoice.objects.get(alias_id=item.get('creditinvoice'))
                
                InvoiceChequeMap.objects.create(
                    cheque_store=instance,
                    creditinvoice=credit_invoice,  # Pass the instance
                    adjusted_amount=item.get('adjusted_amount'),
                    branch=instance.branch,
                    updated_by=instance.updated_by
                )
            except CreditInvoice.DoesNotExist:
                raise ValidationError(
                    f"Credit invoice with ID {item.get('creditinvoice')} does not exist"
                )
            
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={
            'include_invoice_cheques': request.query_params.get('include_invoice_cheques')
        })
        return Response(serializer.data)
    
class InvoiceChequeMapViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.InvoiceChequeMapSerializer
    queryset = InvoiceChequeMap.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        branch = self.request.query_params.get('branch')
        if branch:
            queryset = queryset.filter(branch__alias_id=branch)
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if int(request.data.get('version')) != instance.version:
            return Response({'error': 'Version conflict'}, status=status.HTTP_409_CONFLICT)
        return super().update(request, *args, **kwargs)
    

class ClaimCategoryViewSet(viewsets.ModelViewSet):
    queryset = ClaimCategory.objects.all()
    serializer_class = serializers.ClaimCategorySerializer
    permission_classes = [IsAuthenticated]  # Add this line
    lookup_field = 'alias_id'  

    def get_queryset(self):
        branch = self.request.query_params.get('branch', None)
        if branch:
            return ClaimCategory.objects.filter(branch__alias_id=branch)
        return self.queryset #ClaimCategory.objects.all()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, headers=headers)

    
    def perform_create(self, serializer):
        # Add user tracking
        serializer.save(updated_by=self.request.user)
    
    def perform_update(self, serializer):
        # Add user tracking
        serializer.save(updated_by=self.request.user, version=serializer.instance.version + 1)

class MasterClaimViewSet(viewsets.ModelViewSet):
    queryset = MasterClaim.objects.select_related('branch')
    serializer_class = serializers.MasterClaimSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'alias_id'

    def get_queryset(self):
        queryset = super().get_queryset()
        branch = self.request.query_params.get('branch', None)
        
        if branch:
            queryset = queryset.filter(branch__alias_id=branch)
        
        return queryset.order_by('category', 'claim_name')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(
            updated_by=self.request.user,
            version=1  # Initialize version for new entries
        )

    def perform_update(self, serializer):
        serializer.save(
            updated_by=self.request.user,
            version=serializer.instance.version + 1
        )

class CustomerClaimViewSet(viewsets.ModelViewSet):
    queryset = CustomerClaim.objects.all()
    serializer_class = serializers.CustomerClaimSerializer
    lookup_field = 'alias_id'

    def get_queryset(self):
        queryset = super().get_queryset()
        branch = self.request.query_params.get('branch')
        invoice = self.request.query_params.get('invoice')

        if branch:
            queryset = queryset.filter(branch__alias_id=branch)
        if invoice:
            queryset = queryset.filter(creditinvoice__alias_id=invoice)
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if int(request.data.get('version')) != instance.version:
            return Response({'error': 'Version conflict'}, status=status.HTTP_409_CONFLICT)
        
        return super().update(request, *args, **kwargs)


class CIvsChequeReportView(ViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        

        queryset = CreditInvoice.objects.annotate(
            total_claim=Sum(
                Case(
                    When(
                        Q(customerclaim__claim__category='OTH'),
                        then='customerclaim__claim_amount'
                    ),
                    default=0,
                    output_field=DecimalField(max_digits=18, decimal_places=4)
                )
            ),
            sales_return=Sum(
                Case(
                    When(
                        Q(customerclaim__claim__category='SRTN'),
                        then='customerclaim__claim_amount'
                    ),
                    default=0,
                    output_field=DecimalField(max_digits=18, decimal_places=4)
                )
            ),
            received=Sum(
                Case(
                    When(
                        Q(invoicechequemap__cheque_store__cheque_status__in=[ChequeStore.ChequeStatus.RECEIVED, ChequeStore.ChequeStatus.DEPOSITED]),
                        then='invoicechequemap__adjusted_amount'
                    ),
                    default=0,
                    output_field=DecimalField(max_digits=18, decimal_places=4)
                )
            ),
            cleared=Sum(
                Case(
                    When(
                        Q(invoicechequemap__cheque_store__cheque_status=ChequeStore.ChequeStatus.HONORED),
                        then='invoicechequemap__adjusted_amount'
                    ),
                    default=0,
                    output_field=DecimalField(max_digits=18, decimal_places=4)
                )
            )
        ).select_related('branch')

        # Apply filters
        params = self.request.query_params
        if branch_id := params.get('branch'):
            queryset = queryset.filter(branch__alias_id=branch_id)
        if date_from := params.get('date_from'):
            queryset = queryset.filter(transaction_date__gte=date_from)
        if date_to := params.get('date_to'):
            queryset = queryset.filter(transaction_date__lte=date_to)
        if min_amount := params.get('min_amount'):
            queryset = queryset.filter(due_amount__gte=Decimal(min_amount))
        if max_amount := params.get('max_amount'):
            queryset = queryset.filter(due_amount__lte=Decimal(max_amount))

        return queryset

    def list(self, request):
        queryset = self.get_queryset().annotate(
            net_sales=F('due_amount') - F('sales_return'),
            total_due=F('net_sales') - F('received') - F('cleared') - F('total_claim')
            # net_sales=F('due_amount') - F('total_claim'),
            # total_due=F('net_sales') - (F('received') + F('cleared'))
        ).values(
            'branch__name',
            'invoice_no',
            'transaction_date',
            'payment_grace_days',
            'due_amount',
            'sales_return',
            'net_sales',
            'received',
            'cleared',
            'total_claim',
            'total_due'
        ).order_by('branch__name', 'transaction_date')
        return Response(queryset)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        from openpyxl.worksheet.table import Table, TableStyleInfo
        from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter

        queryset = self.get_queryset().annotate(
            net_sales=F('due_amount') - F('sales_return'),
            total_due=F('net_sales') - F('received') - F('cleared') - F('total_claim')
        ).values(
            'branch__name', 'invoice_no', 'transaction_date', 'payment_grace_days',
            'due_amount', 'sales_return', 'net_sales', 'received', 'cleared',
            'total_claim', 'total_due'
        ).order_by('branch__name', 'transaction_date')

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="ci_report_{datetime.now().strftime("%Y%m%d%H%M")}.xlsx"'

        wb = Workbook()
        ws = wb.active
        ws.title = "CI Cheque Summary" 

        # Custom Styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        alignment = Alignment(horizontal="center", vertical="center")
        thin_border = Border(left=Side(style='thin'), 
                            right=Side(style='thin'), 
                            top=Side(style='thin'), 
                            bottom=Side(style='thin'))
        
        # Column headers
        headers = [
            'Branch Name', 'Invoice No', 'Sales Date', 'Grace',
            'Sale Amount', 'Sales Return', 'Net Sales', 'Received',
            'Cleared', 'Claims', 'Total Due'
        ]
        ws.append(headers)

        # Apply header styling
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = alignment
            cell.border = thin_border

        # Add data rows
        for row_idx, item in enumerate(queryset, start=2):
            row = [
                item['branch__name'],
                item['invoice_no'],
                item['transaction_date'].strftime(settings.DATE_FORMAT),
                item['payment_grace_days'],
                float(item['due_amount'] or 0),
                float(item['sales_return'] or 0),
                float(item['net_sales'] or 0),
                float(item['received'] or 0),
                float(item['cleared'] or 0),
                float(item['total_claim'] or 0),
                float(item['total_due'] or 0)
            ]
            ws.append(row)

            # Apply alternating row colors
            fill_color = "D3D3D3" if row_idx % 2 == 0 else "FFFFFF"
            for col in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col)
                cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
                cell.border = thin_border
                cell.alignment = alignment

        # Set column widths and number formatting
        columns = [
            ('Branch Name', 20),
            ('Invoice No', 15),
            ('Sales Date', 15),
            ('Grace', 10),
            ('Sale Amount', 15),
            ('Sales Return', 15),
            ('Net Sales', 15),
            ('Received', 15),
            ('Cleared', 15),
            ('Claims', 15),
            ('Total Due', 15)
        ]

        for col_num, (title, width) in enumerate(columns, start=1):
            ws.column_dimensions[get_column_letter(col_num)].width = width

        # Apply number formatting
        number_columns = [5, 6, 7, 8, 9, 10, 11]  # Columns E-K
        number_format = '#,##0.' + '0' * settings.DECIMAL_PLACES

        for col_num in number_columns:
            for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_num, max_col=col_num):
                for cell in row:
                    cell.number_format = number_format

        # Create Excel table with filters# Change this line in export_excel():
        #tab = Table(name="InvoiceChequeData", ref=f"A1:{get_column_letter(len(columns))}{len(queryset)+1}")
        tab = Table(displayName="InvoiceChequeData", ref=f"A1:{get_column_letter(len(columns))}{len(queryset)+1}")
        style = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False,
                            showLastColumn=False, showRowStripes=True, showColumnStripes=False)
        tab.tableStyleInfo = style
        ws.add_table(tab)

        wb.save(response)
        return response


    @action(detail=False, methods=['get'])
    def export_pdf(self, request):
        queryset = self.get_queryset().annotate(
            net_sales=F('due_amount') - F('total_claim'),
            total_due=F('net_sales') - (F('received') + F('cleared'))
        ).values(
            'branch__name',
            'invoice_no',
            'transaction_date',
            'due_amount',
            'total_claim',
            'net_sales',
            'received',
            'cleared',
            'total_due'
        )

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="ci_report_{datetime.now().strftime("%Y%m%d%H%M")}.pdf"'

        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # PDF Header
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, height-50, f"CI vs Cheque Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        p.setFont("Helvetica", 10)
        p.drawString(50, height-70, f"Branch Filter: {request.query_params.get('branch', 'All')}")
        p.drawString(50, height-85, f"Date Range: {request.query_params.get('date_from', '')} to {request.query_params.get('date_to', '')}")

        # Create data table
        data = [['Branch', 'Invoice', 'Date', 'Sales Amt', 'Claims','Net', 'Received', 'Cleared',  'Total Due']]
        # Modify the PDF export action
        for item in queryset:
            data.append([
                item['branch__name'],
                item['invoice_no'],
                item['transaction_date'].strftime(settings.DATE_FORMAT),
                f"{item['due_amount']:.{settings.DECIMAL_PLACES}f}",
                f"{item['total_claim']:.{settings.DECIMAL_PLACES}f}",
                f"{item['net_sales']:.{settings.DECIMAL_PLACES}f}",
                f"{item['received']:.{settings.DECIMAL_PLACES}f}",
                f"{item['cleared']:.{settings.DECIMAL_PLACES}f}",
                f"{item['total_due']:.{settings.DECIMAL_PLACES}f}"
            ])
        
        # for item in queryset:
        #     data.append([
        #         item['branch__name'],
        #         item['invoice_no'],
        #         item['transaction_date'].strftime('%Y-%m-%d'),
        #         f"{item['due_amount']:.2f}",
        #         f"{item['total_claim']:.2f}",
        #         f"{item['net_sales']:.2f}",
        #         f"{item['received']:.2f}",
        #         f"{item['cleared']:.2f}",
        #         f"{item['total_due']:.2f}"
        #     ])

        # Create table
        table = Table(data, colWidths=[60, 60, 60, 50, 50, 50, 50, 50, 60])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4472c4')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#d9e1f2')]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))

        # Draw table
        table.wrapOn(p, width-100, height)
        table.drawOn(p, 30, height-120)

        p.showPage()
        p.save()
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)

        return response

