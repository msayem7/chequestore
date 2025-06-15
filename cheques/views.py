# from django.db import IntegrityError
import logging

# --------------------Organized Imports--------------------
# Standard Library Imports
import io
import json
from datetime import datetime, timedelta, date
from decimal import Decimal

# Django Imports
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction, IntegrityError
from django.db.models import (
    F, Sum,Value, DecimalField,IntegerField, ExpressionWrapper, DurationField, DateField,
    Subquery, OuterRef, Q, Case, When
)
from django.db.models.functions import Coalesce, Cast, Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator
from django.utils import timezone
from django_filters import rest_framework as filters
# from django_filters import FilterSet, CharFilter, DateFilter, DecimalFilter
from django_filters.rest_framework import DjangoFilterBackend , FilterSet, CharFilter, DateFilter, NumberFilter


# Django REST Framework Imports
from rest_framework import viewsets, status, filters
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.pagination import PageNumberPagination # Import pagination class

# Third-Party Imports
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from openpyxl import Workbook

# Local Application Imports
from .models import (
    Branch, Customer, CreditInvoice #, CustomerPayment, ChequeStore,
    #CustomerClaim, InvoiceChequeMap, InvoiceClaimMap, MasterClaim
)
from .models import PaymentInstrument, Payment, PaymentDetails, PaymentInstrumentType, Claim

from cheques import serializers
from .serializers import ( # You'll need to create these serializers
    ClaimListSerializer, ClaimUpdateSerializer
    #CustomerPaymentSerializer,  #ChequeStoreSerializer, CustomerClaimSerializer,
    # InvoiceChequeMapSerializer, MasterClaimSerializer
)
from .serializers import PaymentInstrumentSerializer, PaymentSerializer, PaymentDetailsSerializer


logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_detail(request):
    serializer = serializers.UserSerializer(request.user)
    return Response(serializer.data)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = serializers.CustomTokenObtainPairSerializer


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

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
    
    class payment:
        PAID = 'paid'
        UNPAID = 'unpaid'
        All = 'all'

    
    def get_queryset(self):
        params = self.request.query_params
        branch = params.get('branch')
        customer = params.get('customer')
        date_from = params.get('transaction_date_after')
        date_to = params.get('transaction_date_before')
        payment_status = params.get('payment', 'all')
        report_date = params.get('report_date')

        queryset = CreditInvoice.objects.all()
        
        # Apply filters
        if branch:
            queryset = queryset.filter(branch__alias_id=branch)
        if date_from:
            queryset = queryset.filter(transaction_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(transaction_date__lte=date_to)

        if customer:
            cust = Customer.objects.filter(alias_id=customer).first()
            if cust and cust.is_parent:
                child_customers = Customer.objects.filter(
                    Q(parent_id=cust))
                queryset = queryset.filter(customer__in=child_customers)
            elif cust and not cust.is_parent:
                queryset = queryset.filter(customer=cust)

        # Handle payment status filter
        if payment_status.lower() == 'unpaid':
            queryset = queryset.filter(payment__isnull=True)
            # Handle matured dues if report_date is provided
            if report_date:
                try:
                    report_date = datetime.strptime(report_date, '%Y-%m-%d').date()
                    # Use ExpressionWrapper to calculate grace date for each invoice
                    queryset = queryset.annotate(
                        grace_date=ExpressionWrapper(
                            F('transaction_date') + timedelta(days=1) * F('payment_grace_days'),
                            output_field=DateField()
                        )
                    ).filter(grace_date__lte=report_date)
                except ValueError:
                    pass  # Ignore invalid date format
        elif payment_status.lower() == 'paid' or payment_status.lower() == 'all':
                pass
        elif payment_status:
                queryset = queryset.filter(payment__alias_id=payment_status)
        
        return queryset.order_by('transaction_date')

    # def get_queryset(self):
    #     params = self.request.query_params
    #     branch = params.get('branch')
    #     customer = params.get('customer')
    #     # status = params.get('status')
    #     date_from = params.get('transaction_date_after')
    #     date_to = params.get('transaction_date_before')
    #     payment = params.get('payment')

    #     queryset = CreditInvoice.objects.all()
        
    #     # Apply filters
    #     if branch:
    #         queryset = queryset.filter(branch__alias_id=branch)
    #     # if customer:
    #     #     queryset = queryset.filter(customer__alias_id=customer)
    #     # if status:
    #     #     is_active = status.lower() == 'true'
    #     #     queryset = queryset.filter(status=is_active)
    #     if date_from:
    #         queryset = queryset.filter(transaction_date__gte=date_from)
    #     if date_to:
    #         queryset = queryset.filter(transaction_date__lte=date_to)

    #     if customer:
    #         cust = Customer.objects.filter(alias_id=customer).first()

    #         if cust and  cust.is_parent:
    #         # If customer is a parent, filter invoices for all child customers
    #             child_customers = Customer.objects.filter(
    #                 Q(parent_id=cust)
    #             )#.values_list('alias_id', flat=True)

    #             queryset = queryset.filter(customer__in=child_customers)
    #         if cust and  cust.is_parent == False:
    #             # If customer is not a parent, filter invoices for that specific customer
    #             queryset = queryset.filter(customer=cust)

    #     if payment:
    #         if payment.lower() == self.payment.PAID:
    #             # Filter for fully paid invoices
    #             queryset = queryset.filter(payment__isnull = False)
    #         elif payment.lower() == self.payment.UNPAID:
    #             # Filter for unpaid invoices
    #             queryset = queryset.filter(payment__isnull = True)
    #         elif payment.lower() == self.payment.All:
    #             # Include all invoices regardless of payment status
    #             pass
    #         else:
    #             payment_id = Payment.objects.filter(alias_id=payment).first()
    #             queryset = queryset.filter(payment = payment_id)

        
    #     # print('This queryset :', print(queryset.query))
    #     return queryset.order_by('transaction_date')

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
        instrument_type_serial_no = self.request.query_params.get('instrument_type_serial_no')
        is_active = self.request.query_params.get('is_active', 'true').lower() == 'true'
        
        
        queryset = queryset.filter(is_active=is_active)

        if branch_id:
            # Use alias_id directly in the filter
            queryset = queryset.filter(branch__alias_id=branch_id)

        if instrument_type_serial_no:
            queryset = queryset.filter(instrument_type__serial_no=instrument_type_serial_no)

        return queryset.order_by('serial_no')
    

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer #PaymentViewSerializer
    lookup_field = 'alias_id'
    
    def get_serializer_class(self):
        # if self.action == 'create':
        #     return PaymentSerializer
        return PaymentSerializer #PaymentViewSerializer
     
    def get_queryset(self):
        queryset = super().get_queryset()

        branch_id = self.request.query_params.get('branch')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        customer_id = self.request.query_params.get('customer')
        # is_fully_allocated = self.request.query_params.get('is_fully_allocated')
        
    
        if branch_id:
            queryset = queryset.filter(branch__alias_id=branch_id)
            
        if date_from:
            queryset = queryset.filter(received_date__gte=date_from)
            
        if date_to:
            queryset = queryset.filter(received_date__lte=date_to)
            
        if customer_id:
            queryset = queryset.filter(customer__alias_id=customer_id)
       
        # print (queryset.query)
        
        return queryset.order_by('-received_date')
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # Get data from the request
        validated_data = request.data
        
        # Extract nested data
        payment_details_data = validated_data.pop('payment_details', [])
        invoices_data = validated_data.pop('invoices', [])
        cash_equivalent_amount = validated_data.pop('cash_equivalent_amount', 0.0)
        total_amount = validated_data.pop('total_amount', 0.0)
        shortage_amount = validated_data.pop('shortage_amount', 0.0)

       
        branch_alias_id = validated_data.get('branch')
        try:
            branch = Branch.objects.get(alias_id=branch_alias_id)
        except Branch.DoesNotExist:
            return Response({"error": f"Branch with alias_id {branch_alias_id} does not exist."}, status=status.HTTP_400_BAD_REQUEST)
        validated_data['branch'] = branch

        customer_alias_id = validated_data.get('customer')
        try:
            customer = Customer.objects.get(alias_id=customer_alias_id)
        except Customer.DoesNotExist:
            return Response({"error": f"Customer with alias_id {customer_alias_id} does not exist."}, status=status.HTTP_400_BAD_REQUEST)
        validated_data['customer'] = customer
         # Create the Payment instance
        payment = Payment.objects.create(**validated_data)

        # Handle PaymentDetails
        errors = {}
        for index, detail_data in enumerate(payment_details_data):
            payment_instrument = detail_data['payment_instrument']

            try:
                instrument = PaymentInstrument.objects.get(id=payment_instrument)
            except Customer.DoesNotExist:
                return Response({"error": f"Instruement with id {payment_instrument} does not exist."}, status=status.HTTP_400_BAD_REQUEST)
            payment_details_data[index]['payment_instrument'] = instrument
            
            # Handle auto-number generation
            if instrument.instrument_type.auto_number:
                locked_type = PaymentInstrumentType.objects.select_for_update().get(pk=instrument.instrument_type.id)
                locked_type.last_number += 1
                detail_data['id_number'] = f"{locked_type.prefix}{locked_type.last_number:04d}"
                locked_type.save()
            else:
                # Check if the ID number is unique within the same branch
                if PaymentDetails.objects.filter(branch=payment.branch, id_number=detail_data.get('id_number')).exists():
                    errors[f'payment_details.{index}.id_number'] = ["This ID number already exists in this branch."]
        
        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        # Create PaymentDetails and claim objects
        for detail_data in payment_details_data:
            payment_details= PaymentDetails.objects.create(payment=payment, branch=payment.branch, **detail_data)
            if instrument.instrument_type.serial_no == 3:
                Claim.objects.create(branch=payment.branch, payment_details = payment_details
                )

        # Update CreditInvoices
        for invoice_data in invoices_data:
            invoice_alias_id = invoice_data.get('alias_id')
            if not invoice_alias_id:
                return Response({"error": "Missing 'alias_id' for one or more invoices"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                invoice = CreditInvoice.objects.get(alias_id=invoice_alias_id)
                invoice.payment = payment # Mark invoice as paid
                invoice.status = True  
                invoice.save()
            except CreditInvoice.DoesNotExist:
                return Response({"error": f"Invoice with alias_id {invoice_alias_id} does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        # Update the Payment amounts
        payment.total_amount = total_amount
        payment.cash_equivalent_amount = cash_equivalent_amount
        payment.shortage_amount = shortage_amount
        payment.save()

        # Return the created payment object with the serializer
        # return Response(PaymentViewSerializer(payment).data, status=status.HTTP_201_CREATED)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
    

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        payment = self.get_object()
        
        # Version check
        client_version = request.data.get('version')
        if client_version and int(client_version) != payment.version:
            return Response(
                {"error": "This payment has been modified by another user. Please refresh."},
                status=status.HTTP_409_CONFLICT
            )

        # Extract data
        validated_data = request.data.copy()
        payment_details_data = validated_data.pop('payment_details', [])
        invoices_data = validated_data.pop('invoices', [])
        
        # Update payment fields
        for field, value in validated_data.items():
            if field in ['branch', 'customer']:
                try:
                    if field == 'branch':
                        obj = Branch.objects.get(alias_id=value)
                    else:
                        obj = Customer.objects.get(alias_id=value)
                    setattr(payment, field, obj)
                except (Branch.DoesNotExist, Customer.DoesNotExist) as e:
                    return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            elif hasattr(payment, field):
                setattr(payment, field, value)

        # Handle payment details updates
        existing_detail_ids = [d.id for d in payment.paymentdetails_set.all()]
        updated_detail_ids = []
        
        for detail_data in payment_details_data:
            detail_id = detail_data.get('id')
            if detail_id and detail_id in existing_detail_ids:
                # Update existing detail
                try:
                    detail = PaymentDetails.objects.get(id=detail_id)
                    instrument = PaymentInstrument.objects.get(id=detail_data['payment_instrument'])
                    
                    # For existing details, don't change ID number
                    for field, value in detail_data.items():
                        if field == 'payment_instrument':
                            setattr(detail, field, instrument)
                        elif field != 'id_number' and hasattr(detail, field):
                            setattr(detail, field, value)
                    detail.save()
                    updated_detail_ids.append(detail.id)
                except (PaymentDetails.DoesNotExist, PaymentInstrument.DoesNotExist):
                    continue
            else:
                # Create new detail
                try:
                    instrument = PaymentInstrument.objects.get(id=detail_data['payment_instrument'])
                    id_number = None
                    
                    # Handle auto-numbering
                    if instrument.instrument_type.auto_number:
                        # Lock the type row to prevent concurrent updates
                        with transaction.atomic():
                            locked_type = PaymentInstrumentType.objects.select_for_update().get(
                                pk=instrument.instrument_type.id
                            )
                            locked_type.last_number += 1
                            id_number = f"{locked_type.prefix}{locked_type.last_number:04d}"
                            locked_type.save()
                    else:
                        id_number = detail_data.get('id_number', '')
                        # Manual ID - check uniqueness
                        if id_number and PaymentDetails.objects.filter(
                            branch=payment.branch, 
                            id_number=id_number
                        ).exists():
                            return Response(
                                {"error": f"ID number {id_number} already exists in this branch"},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    
                    # Create detail
                    detail = PaymentDetails.objects.create(
                        payment=payment,
                        branch=payment.branch,
                        payment_instrument=instrument,
                        id_number=id_number,
                        amount=detail_data.get('amount', 0),
                        detail=detail_data.get('detail', '')
                    )
                    updated_detail_ids.append(detail.id)
                    
                    # Create claim if needed
                    if instrument.instrument_type.serial_no == 3:
                        Claim.objects.create(
                            branch=payment.branch,
                            payment_details=detail
                        )
                            
                except PaymentInstrument.DoesNotExist:
                    continue

        # Delete removed details
        PaymentDetails.objects.filter(payment=payment).exclude(id__in=updated_detail_ids).delete()

        # Handle invoice updates
        existing_invoice_ids = [i.alias_id for i in payment.invoice_set.all()]
        updated_invoice_ids = []
        
        for invoice_data in invoices_data:
            invoice_alias_id = invoice_data.get('alias_id')
            if invoice_alias_id:
                try:
                    invoice = CreditInvoice.objects.get(alias_id=invoice_alias_id)
                    invoice.payment = payment
                    invoice.status = True
                    invoice.save()
                    updated_invoice_ids.append(invoice.alias_id)
                except CreditInvoice.DoesNotExist:
                    continue

        # Unlink removed invoices
        CreditInvoice.objects.filter(
            payment=payment
        ).exclude(
            alias_id__in=updated_invoice_ids
        ).update(
            payment=None,
            status=False
        )

        # Update payment amounts and version
        payment.total_amount = validated_data.get('total_amount', 0)
        payment.cash_equivalent_amount = validated_data.get('cash_equivalent_amount', 0)
        payment.shortage_amount = validated_data.get('shortage_amount', 0)
        payment.version = F('version') + 1
        payment.save()
        payment.refresh_from_db()

        return Response(PaymentSerializer(payment).data)
    
    
        
# class ClaimFilter(FilterSet):
#     customer = CharFilter(field_name='payment_details__payment__customer__alias_id', lookup_expr='icontains')
#     instrument = CharFilter(field_name='payment_details__payment_instrument__serial_no', lookup_expr='exact')
#     claim_date = DateFilter(field_name='payment_details__payment__received_date', lookup_expr='gte')

#     # Range filters for claim_amount, refund_amount, and remaining_amount
#     claim_amount_min = NumberFilter(field_name='payment_details__amount', lookup_expr='gte')  # claim_amount >= min
#     claim_amount_max = NumberFilter(field_name='payment_details__amount', lookup_expr='lte')  # claim_amount <= max
    
#     refund_amount_min = NumberFilter(field_name='refund_amount', lookup_expr='gte')  # refund_amount >= min
#     refund_amount_max = NumberFilter(field_name='refund_amount', lookup_expr='lte')  # refund_amount <= max
    
#     remaining_amount_min = NumberFilter(field_name='remaining_amount', lookup_expr='gte')  # remaining_amount >= min
#     remaining_amount_max = NumberFilter(field_name='remaining_amount', lookup_expr='lte')  # remaining_amount <= max
    

#     class Meta:
#         model = Claim
#         fields = ['customer', 'instrument', 'claim_date', 
#                   'claim_amount_min', 'claim_amount_max', 
#                   'refund_amount_min', 'refund_amount_max', 
#                   'remaining_amount_min', 'remaining_amount_max']

class ClaimFilter(FilterSet):
    customer = CharFilter(field_name='payment_details__payment__customer__alias_id', lookup_expr='icontains')
    instrument = CharFilter(field_name='payment_details__payment_instrument__serial_no', lookup_expr='exact')
    claim_date = DateFilter(field_name='payment_details__payment__received_date', lookup_expr='gte')

    # Range filters for claim_amount, refund_amount, and remaining_amount
    claim_amount_min = NumberFilter(field_name='payment_details__amount', lookup_expr='gte')
    claim_amount_max = NumberFilter(field_name='payment_details__amount', lookup_expr='lte')
    
    refund_amount_min = NumberFilter(field_name='refund_amount', lookup_expr='gte')
    refund_amount_max = NumberFilter(field_name='refund_amount', lookup_expr='lte')
    
    remaining_amount_min = NumberFilter(field_name='remaining_amount', lookup_expr='gte')
    remaining_amount_max = NumberFilter(field_name='remaining_amount', lookup_expr='lte')

    class Meta:
        model = Claim
        fields = [
            'customer', 
            'instrument', 
            'claim_date',
            'claim_amount_min', 
            'claim_amount_max',
            'refund_amount_min', 
            'refund_amount_max',
            'remaining_amount_min', 
            'remaining_amount_max'
        ]

class ClaimViewSet(viewsets.ModelViewSet):
    queryset = Claim.objects.select_related(
        'payment_details__payment__customer',
        'payment_details__payment_instrument',
        'payment_details__payment_instrument__instrument_type',
    ).filter(
        payment_details__payment_instrument__instrument_type__serial_no=3
    ).annotate(
        remaining_amount=ExpressionWrapper(
            F('payment_details__amount') - Coalesce(F('refund_amount'), 0),
            output_field=DecimalField()
        )
    )  # Assuming serial_no 3 is for claims
    # queryset =queryset.filter(instrument_type__serial_no=3)  # Assuming serial_no 3 is for claims
    serializer_class = ClaimListSerializer
    lookup_field = 'alias_id'

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ClaimFilter
    # filterset_fields = {
    #     'payment_details__payment__customer__alias_id': ['icontains'],
    #     'payment_details__payment_instrument__instrument_name': ['icontains'],
    #     'payment_details__payment__received_date': ['lte'], #['exact', 'gte', 'lte'],
    # }
    search_fields = [
        'payment_details__payment__customer__alias_id',
        'payment_details__payment_instrument__instrument_name',
    ]
    # Add this line to enable pagination for this ViewSet
    # pagination_class = StandardResultsSetPagination

    # def get_queryset(self):
    #     queryset = super().get_queryset()

    #     branch_id = self.request.query_params.get('branch')
    #     date_from = self.request.query_params.get('date_from')
    #     date_to = self.request.query_params.get('date_to')
    #     customer_id = self.request.query_params.get('customer')
    #     # is_fully_allocated = self.request.query_params.get('is_fully_allocated')
        
    
    #     if branch_id:
    #         queryset = queryset.filter(branch__alias_id=branch_id)
            
    #     if date_from:
    #         queryset = queryset.filter(received_date__gte=date_from)
            
    #     if date_to:
    #         queryset = queryset.filter(received_date__lte=date_to)
            
    #     if customer_id:
    #         queryset = queryset.filter(customer__alias_id=customer_id)
       
    #     # print (queryset.query)
        
    #     return queryset.order_by('-received_date')

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return ClaimUpdateSerializer
        return ClaimListSerializer

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def update_claim(self, request, *args, **kwargs):
        claim = self.get_object()
        serializer = self.get_serializer(claim, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user, version=claim.version + 1)
        return Response(serializer.data)
    
# ----------------- end of payment implementation---------------------


# --------Latest:01  parent customer due
class ParentCustomerDueReport(APIView):
    def get(self, request):
        report_date_str = request.query_params.get('date')
        branch_alias_id = request.query_params.get('branch')  # New branch filter

        if branch_alias_id is None:
            return Response(
                {"error": "Banch Id is mandatory"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            report_date = timezone.datetime.strptime(report_date_str, '%Y-%m-%d').date() if report_date_str else timezone.now().date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        
        customer_qs = Customer.objects.all()
        invoice_qs = CreditInvoice.objects.all()
        
        # Apply branch filter if provided
        if branch_alias_id:
            customer_qs = customer_qs.filter(branch__alias_id=branch_alias_id)
            invoice_qs = invoice_qs.filter(branch__alias_id=branch_alias_id)
        
        # Query 1: Get all parent-child relationships with alias_id
        customer_hierarchy = Customer.objects.filter(
            ( Q(is_parent=True) | Q(parent__isnull=False))
        ).values('alias_id', 'name', 'is_parent', 'parent__alias_id', 'parent__name')
        
        # Query 2: Get all due invoice amounts grouped by customer
        due_amounts = CreditInvoice.objects.filter(
            customer__parent__isnull=False,  # Only child customers
            transaction_date__lte=report_date
        ).filter(
            Q(payment__isnull=True) |
            Q(payment__received_date__gt=report_date)
        ).annotate(
            is_matured=Case(
                When(transaction_date__lte=report_date-F('payment_grace_days'),
                     then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )
        ).values('customer__alias_id').annotate(
            matured_due=Sum('sales_amount', filter=Q(is_matured=1)),
            immature_due=Sum('sales_amount', filter=Q(is_matured=0))
        )
        
        # Process in Python
        parents = {c['alias_id']: c for c in customer_hierarchy if c['is_parent']}
        children = {c['alias_id']: c for c in customer_hierarchy if not c['is_parent']}
        
        report_data = []
        grand_total_matured = 0
        grand_total_immature = 0
        grand_total_due = 0
        
        for parent in parents.values():
            parent_entry = {
                'alias_id': parent['alias_id'],
                'name': parent['name'],
                'matured_due': 0,
                'immature_due': 0,
                'total_due': 0,
                'children': []
            }
            
            for child in children.values():
                if child['parent__alias_id'] == parent['alias_id']:
                    amounts = next(
                        (a for a in due_amounts 
                         if a['customer__alias_id'] == child['alias_id']), 
                        {}
                    )
                    child_entry = {
                        'alias_id': child['alias_id'],
                        'name': child['name'],
                        'matured_due': amounts.get('matured_due', Decimal(0)) or Decimal(0), 
                        'immature_due': amounts.get('immature_due', Decimal(0)) or Decimal(0)
                    }
                    child_entry['total_due'] = child_entry['matured_due'] + child_entry['immature_due']
                    parent_entry['children'].append(child_entry)
                    parent_entry['matured_due'] += child_entry['matured_due']
                    parent_entry['immature_due'] += child_entry['immature_due']
                    parent_entry['total_due'] += child_entry['total_due']
                    
                    grand_total_matured += child_entry['matured_due']
                    grand_total_immature += child_entry['immature_due']
                    grand_total_due += child_entry['total_due']
            
            report_data.append(parent_entry)
        
        return Response({
            'report_date': report_date.strftime('%Y-%m-%d'),
            'data': report_data,
            'grand_totals': {
                'matured_due': grand_total_matured,
                'immature_due': grand_total_immature,
                'total_due': grand_total_due
            }
        })
    

# class InvoicePaymentReportView(APIView):
#     def get(self, request):
#         customer_id = request.query_params.get('customer_id')
#         start_date = request.query_params.get('start_date')
#         end_date = request.query_params.get('end_date')
#         report_format = request.query_params.get('format', 'html')
        
#         if not customer_id:
#             return Response(
#                 {"error": "Customer ID is required"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         # Build query
#         query = Q(customer__alias_id=customer_id)
        
#         if start_date:
#             try:
#                 start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
#                 query &= Q(transaction_date__gte=start_date)
#             except ValueError:
#                 return Response(
#                     {"error": "Invalid start date format. Use YYYY-MM-DD"},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
                
#         if end_date:
#             try:
#                 end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
#                 query &= Q(transaction_date__lte=end_date)
#             except ValueError:
#                 return Response(
#                     {"error": "Invalid end date format. Use YYYY-MM-DD"},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#         invoices = CreditInvoice.objects.filter(query).order_by('transaction_date')
        
#         # Calculate totals
#         for invoice in invoices:
            
#             cheque_allocated = invoice.cheque_allocations.aggregate(
#                 total=Sum('adjusted_amount')
#             )['total'] or 0 
#             claim_allocated= invoice.claim_allocations.aggregate(
#                 total=Sum('adjusted_amount')
#             )['total'] or 0

#             invoice.total_allocated  = cheque_allocated+claim_allocated
#             invoice.due_amount = invoice.sales_amount - invoice.sales_return - invoice.total_allocated

#         serializer = serializers.InvoicePaymentReportSerializer(invoices, many=True)
       
#         customer = Customer.objects.filter(alias_id=customer_id).first()
#         if report_format == 'json':
#             return Response(serializer.data)
#         else:
#             # For HTML, Excel, PDF - we'll handle in the frontend
#             return Response({
#                 'data': serializer.data,
#                 'customer': invoices[0].customer.name if invoices else '',
#                 'start_date': start_date,
#                 'end_date': end_date
#             })

    