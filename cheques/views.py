# --------------------Organized Imports--------------------
# Standard Library Imports
import io
import json
from datetime import datetime, timedelta, date
from decimal import Decimal

# Django Imports
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import (
    F, Sum,Value, DecimalField, ExpressionWrapper, DurationField, DateField,
    Subquery, OuterRef, Q, Case, When
)
from django.db.models.functions import Coalesce, Cast, Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator


# Django REST Framework Imports
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework_simplejwt.views import TokenObtainPairView
from django_filters import rest_framework as filters

# Third-Party Imports
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from openpyxl import Workbook

# Local Application Imports
from .models import (
    Branch, Customer, CreditInvoice, CustomerPayment, ChequeStore,
    CustomerClaim, InvoiceChequeMap, InvoiceClaimMap, MasterClaim
)
from .models import PaymentInstrument, Payment, PaymentDetails, PaymentInstrumentType

from cheques import serializers
from .serializers import ( # You'll need to create these serializers
    BranchSerializer, CustomerSerializer, CreditInvoiceSerializer,
    CustomerPaymentSerializer, ChequeStoreSerializer, CustomerClaimSerializer,
    InvoiceChequeMapSerializer, MasterClaimSerializer
)
from .serializers import PaymentInstrumentSerializer, PaymentViewSerializer, PaymentCreateSerializer, PaymentDetailsSerializer


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

        queryset = queryset.annotate(
            sort_order=Case(
                When(parent__name__isnull=True, then=F('name')),
                default=Concat('parent__name', 'name')
            )
        ).order_by('sort_order')
        
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

# payment implemente here 
PaymentInstrumentType

class PaymentInstrumentTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PaymentInstrumentType.objects.all()
    serializer_class = serializers.PaymentInstrumentTypeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = self.request.query_params.get('branch')

        if branch_id:
            # Use alias_id directly in the filter
            queryset = queryset.filter(branch__alias_id=branch_id)
            
        return queryset.order_by('serial_no')
    
   
    
class PaymentInstrumentsViewSet(viewsets.ModelViewSet):
    queryset = PaymentInstrument.objects.all()
    serializer_class = PaymentInstrumentSerializer
    # Remove filterset_fields since we'll handle filtering manually
    # filterset_fields= ['branch', 'is_active']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = self.request.query_params.get('branch')
        is_active = self.request.query_params.get('is_active', 'true').lower() == 'true'
        
        queryset = queryset.filter(is_active=is_active)

        if branch_id:
            # Use alias_id directly in the filter
            queryset = queryset.filter(branch__alias_id=branch_id)
            
        return queryset.order_by('serial_no')
    
# In views.py - update PaymentViewSet
class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentViewSerializer
    lookup_field = 'alias_id'
    # filterset_fields = ['customer', 'received_date']
    
    def get_serializer_class(self):
        if self.action == 'create':  # If it's a POST request (Create)
            return PaymentCreateSerializer
        return PaymentViewSerializer  # Default to the UserReadSerializer for GET requests
    
    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = self.request.query_params.get('branch')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        customer_id = self.request.query_params.get('customer')
        is_fully_allocated = self.request.query_params.get('is_fully_allocated')
        
    
        if branch_id:
            queryset = queryset.filter(branch__alias_id=branch_id)
            
        if date_from:
            queryset = queryset.filter(received_date__gte=date_from)
            
        if date_to:
            queryset = queryset.filter(received_date__lte=date_to)
            
        if customer_id:
            queryset = queryset.filter(customer__alias_id=customer_id)
            
        # Annotate with payment totals
        # queryset = queryset.annotate(
        #     total_payment=Sum('paymentdetails__amount')
            
        # )
        
        # Filter by allocation status if provided
        if is_fully_allocated and is_fully_allocated.lower() != 'all':
            if is_fully_allocated.lower() == 'yes':
                queryset = queryset.filter(paymentdetails__is_allocated=True).distinct()
            elif is_fully_allocated.lower() == 'no':
                queryset = queryset.filter(paymentdetails__is_allocated=False).distinct()
        
        # print (queryset.query)
        
        return queryset.order_by('-received_date')
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    # @transaction.atomic
    # def create(self, request, *args, **kwargs):
    #     # Let the serializer handle payment_details
    #     payment = super().create(request, *args, **kwargs)
        
    #     # Process auto_number for each payment detail
    #     for detail in payment.paymentdetails_set.all():
    #         instrument_type = detail.payment_instrument.instrument_type
    #         if instrument_type.auto_number:
    #             with transaction.atomic():
    #                 locked_type = PaymentInstrumentType.objects.select_for_update().get(id=instrument_type.id)
    #                 locked_type.last_number += 1
    #                 detail.id_number = f"{locked_type.prefix}{locked_type.last_number:04d}"
    #                 detail.save()
    #                 locked_type.save()
        
    #     return payment
    # @transaction.atomic
    # def create(self, request, *args, **kwargs):
    #     # payment_details_data = request.data.pop('payment_details', [])
    #     payment = super().create(request, *args, **kwargs)
        
    #     # Process payment details with atomic transaction
    #     for detail_data in payment_details_data:
    #         instrument_type = PaymentInstrument.objects.get(
    #             id=detail_data['payment_instrument']
    #         ).instrument_type
            
    #         if instrument_type.auto_number:
    #             # with transaction.atomic():
    #                 # Lock the instrument type for update
    #             locked_type = PaymentInstrumentType.objects.select_for_update().get(
    #                 id=instrument_type.id
    #             )
    #             locked_type.last_number += 1
    #             detail_data['id_number'] = f"{locked_type.prefix}{locked_type.last_number:04d}"
    #             locked_type.save()
    #         else:
    #             # Manual entry - already validated by serializer
    #             pass
            
    #         PaymentDetails.objects.create(payment=payment, **detail_data)
        
    #     return payment
    

# ----------------- end of payment implementation---------------------

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

@api_view(['GET'])
def unallocated_payments(request):
    branch = request.query_params.get('branch')
    customer = request.query_params.get('customer')
    
    if not branch or not customer:
        return Response({'error': 'Branch and customer parameters are required'}, status=400)
    
    payments = ChequeStore.objects.filter(
        branch__alias_id=branch,
        customer_payment__customer__alias_id=customer
    ).annotate(
        allocated=Sum(Coalesce('invoice_cheques__adjusted_amount', Decimal(0)))
    ).filter(
        cheque_amount__gt=F('allocated') or 0
    )
    # print(payments.query)
    serializer = ChequeStoreSerializer(payments, many=True)
    # print(serializer.data)
    return Response(serializer.data)


class CustomerPaymentViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.CustomerPaymentSerializer
    queryset = CustomerPayment.objects.all()
    lookup_field = 'alias_id'

    def get_queryset(self):
        return self.queryset.filter(
            branch__alias_id=self.request.query_params.get('branch')
        ).select_related('customer', 'branch')
    
    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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
            # Convert string dates to date objects (not datetime)
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            
            # Get the customer and branch
            customer = Customer.objects.get(alias_id=customer_id, branch__alias_id=branch_id)
            branch = Branch.objects.get(alias_id=branch_id)
            
            # Calculate opening balance
            opening_balance = self._calculate_opening_balance(customer, branch, from_date)
            
            # Get sales transactions with calculated payment date
            sales_data = CreditInvoice.objects.filter(
                customer=customer,
                branch=branch
            ).annotate(
                payment_date=ExpressionWrapper(
                    F('transaction_date') + timedelta(days=1) * F('payment_grace_days'),
                    output_field=DateField()
                ),
                net_sales=F('sales_amount') - F('sales_return')
            ).filter(
                payment_date__gte=from_date,
                payment_date__lte=to_date
            ).values(
                'transaction_date',
                'payment_date',
                'grn',
                'transaction_details',
                'sales_amount',
                'sales_return',
                'net_sales',
                'payment_grace_days'
            )
            
            # Get cheque transactions
            # Get cheque transactions with proper field aliasing
            cheque_data = ChequeStore.objects.filter(
                customer_payment__customer=customer,
                branch=branch,
                customer_payment__received_date__gte=from_date,
                customer_payment__received_date__lte=to_date
            ).select_related('customer_payment').values(
                'instrument_type', 
                'receipt_no',
                'cheque_detail',
                'cheque_amount',
                received_date=F('customer_payment__received_date')
            )
            
            # Get claim transactions
            claim_data = CustomerClaim.objects.filter(
                customer_payment__customer=customer,
                branch=branch,
                customer_payment__received_date__gte=from_date,
                customer_payment__received_date__lte=to_date
            ).select_related('customer_payment', 'claim').values(
                'claim_no',
                'details',
                'claim_amount',
                received_date=F('customer_payment__received_date')
            )
            
            # Prepare statement data
            statement_data = []
            current_balance = opening_balance

            INSTRUMENT_TYPE_NAMES = {
                1: 'Cash',
                2: 'Cheque',
                3: 'Pay Order',  # For Demand Draft
                4: 'EFT',
                5: 'RTGS'
            }
            # Add opening balance row
            statement_data.append({
                'transaction_type_id': 0,
                'transaction_type_name': 'Opening Balance',
                'date': from_date,
                'particular': 'Opening Balance',
                'sales_amount': Decimal('0'),
                'sales_return': Decimal('0'),
                'net_sales': Decimal('0'),
                'received': Decimal('0'),
                'balance': opening_balance
            })
            
            # Process sales transactions
            for sale in sales_data:
                # current_balance += sale['net_sales']
                transaction_date = sale['transaction_date']
                if isinstance(transaction_date, datetime):
                    transaction_date = transaction_date.date()
                
                payment_date = sale['payment_date']
                if isinstance(payment_date, datetime):
                    payment_date = payment_date.date()
                
                particular = (
                    f"Invoice No: {sale['grn']}, "
                    f"Sales Date: {transaction_date.strftime('%Y-%m-%d')}, "
                    f"Due Date: {payment_date.strftime('%Y-%m-%d')}, "
                    f"Grace Days: {sale['payment_grace_days']}, "
                    f"Details: {sale['transaction_details'] or ''}"
                )
                statement_data.append({
                    'transaction_type_id': 1,
                    'transaction_type_name': 'Sales',
                    'date': payment_date,
                    'particular': particular.strip(),
                    'sales_amount': sale['sales_amount'],
                    'sales_return': sale['sales_return'],
                    'net_sales': sale['net_sales'],
                    'received': Decimal('0'),
                    'balance': 0
                    # 'balance': current_balance
                })
            
            # Process cheque transactions
            for cheque in cheque_data:
                # current_balance -= cheque['cheque_amount']
                received_date = cheque['received_date']
                if isinstance(received_date, datetime):
                    received_date = received_date.date()
                
                particular = f"{cheque['receipt_no']} {cheque['cheque_detail'] or ''}"
                instrument_type_name = INSTRUMENT_TYPE_NAMES.get(cheque['instrument_type'], 'Unknown')
                statement_data.append({
                    'transaction_type_id': 2,
                    'transaction_type_name': instrument_type_name,
                    'date': received_date,
                    'particular': particular.strip(),
                    'sales_amount': Decimal('0'),
                    'sales_return': Decimal('0'),
                    'net_sales': Decimal('0'),
                    'received': cheque['cheque_amount'],
                    'balance': 0
                    # 'balance': current_balance
                })
            
            # Process claim transactions
            for claim in claim_data:
                # current_balance -= claim['claim_amount']
                received_date = claim['received_date']
                if isinstance(received_date, datetime):
                    received_date = received_date.date()
                
                particular = f"Claim No: {claim['claim_no']} {claim['details'] or ''}"
                
                statement_data.append({
                    'transaction_type_id': 3,
                    'transaction_type_name': 'Claim',
                    'date': received_date,
                    'particular': particular.strip(),
                    'sales_amount': Decimal('0'),
                    'sales_return': Decimal('0'),
                    'net_sales': Decimal('0'),
                    'received': claim['claim_amount'],
                    'balance': 0
                    # 'balance': current_balance
                })
            
            # Sort by date and transaction type
            statement_data.sort(key=lambda x: (x['date'], x['transaction_type_id']))
            for tr in statement_data:
                 tr['balance'] =  current_balance+ tr['net_sales'] - tr['received']   
                 current_balance = tr['balance']
                  
            # print (statement_data)
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
    
    def _calculate_opening_balance(self, customer, branch, cutoff_date):
        """Calculate opening balance as of cutoff_date"""
        # Sum all sales with payment date before cutoff
        sales_before = CreditInvoice.objects.filter(
            customer=customer,
            branch=branch
        ).annotate(
            payment_date=ExpressionWrapper(
                F('transaction_date') + timedelta(days=1) * F('payment_grace_days'),
                output_field=DateField()
            )
        ).filter(
            payment_date__lt=cutoff_date
        ).aggregate(
            total_sales=Coalesce(Sum('sales_amount'), Decimal('0')),
            total_returns=Coalesce(Sum('sales_return'), Decimal('0'))
        )
        
        # Sum all payments before cutoff date
        payments_before = CustomerPayment.objects.filter(
            customer=customer,
            branch=branch,
            received_date__lt=cutoff_date
        ).aggregate(
            total_cheques=Coalesce(
                Sum('chequestore__cheque_amount'),
                Decimal('0')
            ),
            total_claims=Coalesce(
                Sum('customerclaim__claim_amount'),
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
    
# Parent Org wise due reports
class ParentDueReportView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        branch_alias = request.query_params.get('branch')
        cutoff_date = request.query_params.get('cutoff_date', '2050-12-31')
        sort_by = request.query_params.get('sort_by', 'due')

        try:
            if not branch_alias:
                return Response({"error": "Branch parameter is required"}, status=400)

            branch = Branch.objects.get(alias_id=branch_alias)
            parent_org_dues = self._get_parent_org_dues(branch.id, cutoff_date, sort_by)
            
            return Response({
                'success': True,
                'data': parent_org_dues,
                'meta': {
                    'branch': branch.name,
                    'cutoff_date': cutoff_date,
                    'total_due': sum(item['due'] for item in parent_org_dues),
                    'count': len(parent_org_dues)
                }
            }, status=200)
            
        except Branch.DoesNotExist:
            return Response({"error": "Branch not found"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    def _get_parent_org_dues(self, branch_id, end_date='2050-12-31', sort_by='due'):
        """
        Get parent organization dues with sorting options
        
        Parameters:
        - branch_id: Branch ID to filter by
        - end_date: Cutoff date (default: '2050-12-31')
        - sort_by: Sorting option ('due' for due amount descending or 'name' for name ascending)
        """
        # Validate sort_by parameter
        valid_sort_options = ['due', 'name']
        if sort_by not in valid_sort_options:
            raise ValueError(f"Invalid sort_by parameter. Must be one of: {valid_sort_options}")

        # Cheque Received subquery
        cheque_received = CustomerPayment.objects.filter(
            branch_id=branch_id,
            received_date__lte=end_date
        ).values('customer_id').annotate(
            received=Sum('chequestore__cheque_amount', output_field=DecimalField(max_digits=18, decimal_places=4))
        )

        # Claim Received subquery
        claim_received = CustomerPayment.objects.filter(
            branch_id=branch_id,
            received_date__lte=end_date
        ).values('customer_id').annotate(
            received=Sum('customerclaim__claim_amount', output_field=DecimalField(max_digits=18, decimal_places=4))
        )

        # Invoice subquery
        invoice = CreditInvoice.objects.filter(
            branch_id=branch_id,
            transaction_date__lte=end_date
        ).values('customer_id').annotate(
            net_sales=Sum(
                F('sales_amount') - F('sales_return'),
                output_field=DecimalField(max_digits=18, decimal_places=4)
            )
        )

        # Combine all results and group by parent organization
        from collections import defaultdict
        
        # Create a dictionary to store results by parent organization
        parent_org_results = defaultdict(lambda: {
            'parent_org_alias_id': '',
            'parent_org_name': '',
            'net_sales': Decimal('0'),
            'cash': Decimal('0'),
            'claim': Decimal('0'),
            'due': Decimal('0')
        })
        
        # Get all unique customer IDs
        all_customers = set()
        all_customers.update(item['customer_id'] for item in cheque_received)
        all_customers.update(item['customer_id'] for item in claim_received)
        all_customers.update(item['customer_id'] for item in invoice)
        
        # Prefetch parent information for all customers
        customers_with_parents = Customer.objects.filter(
            id__in=all_customers,
            parent__isnull=False
        ).select_related('parent')
        
        # Create mapping of customer to parent
        customer_parent_map = {
            cust.id: cust.parent 
            for cust in customers_with_parents
        }
        
        # Process each customer
        for customer_id in all_customers:
            parent = customer_parent_map.get(customer_id)
            if not parent:
                continue  # Skip customers without parent
            
            # Find matching records in each queryset
            cheque_data = next((item for item in cheque_received if item['customer_id'] == customer_id), {'received': Decimal('0')})
            claim_data = next((item for item in claim_received if item['customer_id'] == customer_id), {'received': Decimal('0')})
            invoice_data = next((item for item in invoice if item['customer_id'] == customer_id), {'net_sales': Decimal('0')})
            
            # Calculate values
            net_sales = invoice_data.get('net_sales', Decimal('0'))
            cash = cheque_data.get('received', Decimal('0'))
            claim = claim_data.get('received', Decimal('0'))
            due = net_sales - cash - claim
            
            # Add to parent organization totals
            parent_org_results[parent.id]['parent_org_alias_id'] = parent.alias_id
            parent_org_results[parent.id]['parent_org_name'] = parent.name
            parent_org_results[parent.id]['net_sales'] += net_sales
            parent_org_results[parent.id]['cash'] += cash
            parent_org_results[parent.id]['claim'] += claim
            parent_org_results[parent.id]['due'] += due
        
        # Convert to list of dictionaries
        results = list(parent_org_results.values())
        
        # Apply sorting
        if sort_by == 'due':
            results.sort(key=lambda x: x['due'], reverse=True)  # Descending order
        elif sort_by == 'name':
            results.sort(key=lambda x: x['parent_org_name'].lower())  # Case-insensitive ascending
        
        return results

# Customer Hierarchy wise due reports
   

@api_view(['GET'])
def parent_customer_due_report(request):
    try:

        branch_alias = request.query_params.get('branch_id')
        end_date = request.query_params.get('end_date', '2023-12-31')
        
        if not branch_alias:
            return Response({"error": "Branch parameter is required"}, status=400)

        branch = Branch.objects.get(alias_id=branch_alias)      
        
        # with connection.cursor() as cursor:
        #     cursor.callproc('get_parent_customer_due', [branch_id, end_date])
            # rows = cursor.fetchall()

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM get_parent_customer_due(%s, %s)",
                [branch.id, end_date]
            )
            columns = [col[0] for col in cursor.description]
            data = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]
           
        return Response(data)
    
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    


class InvoicePaymentReportView(APIView):
    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        report_format = request.query_params.get('format', 'html')
        
        if not customer_id:
            return Response(
                {"error": "Customer ID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Build query
        query = Q(customer__alias_id=customer_id)
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                query &= Q(transaction_date__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "Invalid start date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                query &= Q(transaction_date__lte=end_date)
            except ValueError:
                return Response(
                    {"error": "Invalid end date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        invoices = CreditInvoice.objects.filter(query).order_by('transaction_date')
        
        # Calculate totals
        for invoice in invoices:
            
            cheque_allocated = invoice.cheque_allocations.aggregate(
                total=Sum('adjusted_amount')
            )['total'] or 0 
            claim_allocated= invoice.claim_allocations.aggregate(
                total=Sum('adjusted_amount')
            )['total'] or 0

            invoice.total_allocated  = cheque_allocated+claim_allocated
            invoice.due_amount = invoice.sales_amount - invoice.sales_return - invoice.total_allocated

        serializer = serializers.InvoicePaymentReportSerializer(invoices, many=True)
       
        customer = Customer.objects.filter(alias_id=customer_id).first()
        if report_format == 'json':
            return Response(serializer.data)
        else:
            # For HTML, Excel, PDF - we'll handle in the frontend
            return Response({
                'data': serializer.data,
                'customer': invoices[0].customer.name if invoices else '',
                'start_date': start_date,
                'end_date': end_date
            })