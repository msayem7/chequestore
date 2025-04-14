
# from .models import 
# from .serializers import CustomerPaymentSerializer
# from django.db import transaction
# Standard library imports
import io
import json
from datetime import datetime
from decimal import Decimal

# Django imports
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Case, When, Q, F, DecimalField, ExpressionWrapper
from django.db.models import Subquery, OuterRef
from django.db.models.functions import Coalesce
from django.db import transaction
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator  # 👈 Add this import

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
    Branch, Customer, CreditInvoice,
    ChequeStore, InvoiceChequeMap, InvoiceClaimMap, 
    MasterClaim, CustomerClaim, CustomerPayment
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_detail(request):
    serializer = serializers.UserSerializer(request.user)
    return Response(serializer.data)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = serializers.CustomTokenObtainPairSerializer

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
         
        #if not self.request.user.is_staff:  # Example: admins see all
        if self.request.query_params.get('is_active'):
            is_active = self.request.query_params.get('is_active', 'true').lower() == 'true'
            # print('is_active',is_active, 'self.request.query_params.get', self.request.query_params.get('is_active', 'true').lower())
            queryset = queryset.filter(is_active=is_active)
        
        # Filter by branch alias_id
        if branch_id:
            queryset = queryset.filter(branch__alias_id=branch_id)
            
        # Filter parent customers
        if self.request.query_params.get('is_parent'):
            is_parent = self.request.query_params.get('is_parent', 'true').lower() == 'true'
            queryset = queryset.filter(is_parent=is_parent)
        
        # print('queryset :', print(str(queryset.query)))
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
            # Check for credit invoices or cheque stores related to this customer
            has_activity = (
                CreditInvoice.objects.filter(customer=customer).exists() or
                ChequeStore.objects.filter(customer_payment__customer=customer).exists()
            )
            return has_activity
        except Customer.DoesNotExist:
            return False
        
class CreditInvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.CreditInvoiceSerializer
    queryset = CreditInvoice.objects.all()
    lookup_field = 'alias_id'
    
    def get_queryset(self):

        # Subquery for cheque allocations
        cheque_subquery = (
            InvoiceChequeMap.objects
            .filter(credit_invoice=OuterRef('pk'))
            .values('credit_invoice')
            .annotate(total=Sum('adjusted_amount'))
            .values('total')
        )

        # Subquery for claim allocations
        claim_subquery = (
            InvoiceClaimMap.objects
            .filter(credit_invoice=OuterRef('pk'))
            .values('credit_invoice')
            .annotate(total=Sum('adjusted_amount'))
            .values('total')
        )

        queryset = CreditInvoice.objects.annotate(
            cheque_allocated=Coalesce(
                Subquery(cheque_subquery, output_field=DecimalField()),
                Decimal('0.0')
            ),
            claim_allocated=Coalesce(
                Subquery(claim_subquery, output_field=DecimalField()),
                Decimal('0.0')
            ),
            total_allocated=F('cheque_allocated') + F('claim_allocated'),
            net_due=F('sales_amount') - F('sales_return') - F('total_allocated')
        )
        params = self.request.query_params
        branch = params.get('branch')
        customer = params.get('customer')
        status = params.get('status')
        date_from = params.get('transaction_date_after')
        date_to = params.get('transaction_date_before')

        # Apply filters
        if branch:
            queryset = queryset.filter(branch__alias_id=branch)
        if customer:
            queryset = queryset.filter(customer__alias_id=customer)
        if status:
            is_active = status.lower() == 'true'
            queryset = queryset.filter(status=is_active)
        if date_from:
            queryset = queryset.filter(transaction_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(transaction_date__lte=date_to)

        # print ('queryset :', print(str(queryset.query)))
        return queryset.order_by('transaction_date')
     

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


    @method_decorator(never_cache)  # 👈 Disable caching
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if latest := self.get_queryset().order_by('-transaction_date').first():
            response.headers['Last-Modified'] = latest.updated_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response


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
        
        return queryset.order_by('claim_name')

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
    lookup_field = 'claim_no'

    def get_queryset(self):
        queryset = super().get_queryset()
        branch = self.request.query_params.get('branch')
        invoice = self.request.query_params.get('invoice')
        # add filter using invoice__receipt_no

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

class CustomerPaymentViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.CustomerPaymentSerializer
    queryset = CustomerPayment.objects.all()
    lookup_field = 'alias_id'

    def get_queryset(self):
        return self.queryset.filter(
            branch__alias_id=self.request.query_params.get('branch')
        ).select_related('customer', 'branch')
    
# class CustomerPaymentViewSet(viewsets.ModelViewSet):
#     serializer_class = serializers.CustomerPaymentSerializer
#     queryset = CustomerPayment.objects.all()
#     lookup_field = 'alias_id'

#     def get_queryset(self):
#         return self.queryset.filter(
#             branch__alias_id=self.request.query_params.get('branch')
#         ).select_related('customer', 'branch')

#     @transaction.atomic
#     def perform_create(self, serializer):
#         serializer.save(
#             updated_by=self.request.user,
#             branch_id=self.request.data.get('branch')
#         )
# Add to views.py
class CustomerStatementViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        # Get query parameters
        branch_id = request.query_params.get('branch')
        customer_id = request.query_params.get('customer')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        if not all([branch_id, customer_id, date_from, date_to]):
            return Response(
                {'error': 'Customer, date_from and date_to parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the customer and branch
            customer = Customer.objects.get(alias_id=customer_id, branch__alias_id=branch_id)
            branch = Branch.objects.get(alias_id=branch_id)
            
            # Calculate opening balance (all transactions before date_from)
            opening_balance = self._calculate_opening_balance(customer, branch, date_from)
            
            # Get sales transactions
            sales_data = CreditInvoice.objects.filter(
                customer=customer,
                branch=branch,
                transaction_date__gte=date_from,
                transaction_date__lte=date_to
            ).annotate(
                net_sales=F('sales_amount') - F('sales_return')
            ).values(
                'transaction_date',
                'invoice_no',
                'transaction_details',
                'sales_amount',
                'sales_return',
                'net_sales',
            )
            
            # Get cheque transactions
            cheque_data = ChequeStore.objects.filter(
                customer_payment__customer=customer,
                branch=branch,
                customer_payment__received_date__gte=date_from,
                customer_payment__received_date__lte=date_to
            ).select_related('customer_payment').values(
                'customer_payment__received_date',
                'cheque_no',
                'cheque_detail',
                'cheque_amount'
            )
            
            # Get claim transactions
            claim_data = CustomerClaim.objects.filter(
                customer_payment__customer=customer,
                branch=branch,
                customer_payment__received_date__gte=date_from,
                customer_payment__received_date__lte=date_to
            ).select_related('customer_payment', 'claim').values(
                'customer_payment__received_date',
                'claim_no',
                'details',
                'claim_amount'
            )
            
            # Prepare statement data
            statement_data = []
            current_balance = opening_balance
            
            # Add opening balance row
            statement_data.append({
                'transaction_type_id': 0,
                'transaction_type_name': 'Opening Balance',
                'date': datetime.strptime(date_from, '%Y-%m-%d').date(),
                'particular': 'Opening Balance',
                'sales_amount': Decimal('0'),
                'sales_return': Decimal('0'),
                'net_sales': Decimal('0'),
                'received': Decimal('0'),
                'balance': opening_balance
            })
            
            # Process sales transactions
            for sale in sales_data:
                current_balance += sale['net_sales']
                particular = f"Invoice No = {sale['invoice_no']} {sale['transaction_details'] or ''}"
                
                statement_data.append({
                    'transaction_type_id': 1,
                    'transaction_type_name': 'Sales',
                    'date': sale['transaction_date'],
                    'particular': particular.strip(),
                    'sales_amount': sale['sales_amount'],
                    'sales_return': sale['sales_return'],
                    'net_sales': sale['net_sales'],
                    'received': Decimal('0'),
                    'balance': current_balance
                })
            
            # Process cheque transactions
            for cheque in cheque_data:
                current_balance -= cheque['cheque_amount']
                particular = f"{cheque['cheque_no']} {cheque['cheque_detail'] or ''}"
                
                statement_data.append({
                    'transaction_type_id': 2,
                    'transaction_type_name': 'Cheque',
                    'date': cheque['customer_payment__received_date'],
                    'particular': particular.strip(),
                    'sales_amount': Decimal('0'),
                    'sales_return': Decimal('0'),
                    'net_sales': Decimal('0'),
                    'received': cheque['cheque_amount'],
                    'balance': current_balance
                })
            
            # Process claim transactions
            for claim in claim_data:
                current_balance -= claim['claim_amount']
                particular = f"Claim No: {claim['claim_no']} {claim['details'] or ''}"
                
                statement_data.append({
                    'transaction_type_id': 3,
                    'transaction_type_name': 'Claim',
                    'date': claim['customer_payment__received_date'],
                    'particular': particular.strip(),
                    'sales_amount': Decimal('0'),
                    'sales_return': Decimal('0'),
                    'net_sales': Decimal('0'),
                    'received': claim['claim_amount'],
                    'balance': current_balance
                })
            
            # Sort by date and transaction type
            statement_data.sort(key=lambda x: (x['date'], x['transaction_type_id']))
            
            # Serialize the data
            serializer = serializers.CustomerStatementSerializer(statement_data, many=True)
            
            return Response({
                'opening_balance': opening_balance,
                'closing_balance': current_balance,
                'transactions': serializer.data
            })
            
        except Customer.DoesNotExist:
            return Response(
                {'error': 'Customer not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Branch.DoesNotExist:
            return Response(
                {'error': 'Branch not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _calculate_opening_balance(self, customer, branch, date_from):
        """Calculate opening balance as of date_from"""
        # Sum all sales before date_from
        print('customer', customer, 'branch', branch, 'date_from', date_from)
        sales_before = CreditInvoice.objects.filter(
            customer=customer,
            branch=branch,
            transaction_date__lt=date_from
        ).aggregate(
            total_sales=Coalesce(Sum('sales_amount'), Decimal('0')),
            total_returns=Coalesce(Sum('sales_return'), Decimal('0'))
        )
        
        # Sum all payments before date_from
        payments_before = CustomerPayment.objects.filter(
            customer=customer,
            branch=branch,
            received_date__lt=date_from
        ).aggregate(
            total_cheques=Coalesce(
                Sum('chequestore__cheque_amount'),  # Changed from 'cheques__' to 'chequestore__'
                Decimal('0')
            ),
            total_claims=Coalesce(
                Sum('customerclaim__claim_amount'),  # Changed from 'claims__' to 'customerclaim__'
                Decimal('0')
            )
        )
        
        opening_balance = (
            sales_before['total_sales'] - 
            sales_before['total_returns'] - 
            payments_before['total_cheques'] - 
            payments_before['total_claims']
        )
        
        return opening_balance