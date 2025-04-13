
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
        
# class HasCustomerActivity(viewsets.ModelViewSet):
#     queryset = Customer.objects.all()
#     serializer_class = serializers.CustomerSerializer

#     def has_Activity(self, request, *args, **kwargs):
#         try:
#             customer = get_object_or_404(Customer, alias_id=request.parser_context['kwargs']['alias_id'])
#             has_activity = customer.creditinvoice_set.exists() or customer.chequestore_set.exists()
#             return has_activity
#         except Customer.DoesNotExist:
#             return False


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

        return queryset.order_by('transaction_date')
     
        # params = self.request.query_params
        # if branch := params.get('branch'):
        #     queryset = queryset.filter(branch__alias_id=branch)
        # if date_from := params.get('transaction_date_after'):
        #     queryset = queryset.filter(transaction_date__gte=date_from)
        # if date_to := params.get('transaction_date_before'):
        #     queryset = queryset.filter(transaction_date__lte=date_to)
        # if customer := params.get('customer'):
        #     queryset = queryset.filter(customer__alias_id=customer)
        # if status := params.get('status'):
        #     is_active = status.lower() == 'true'  # Corrected filter
        #     queryset = queryset.filter(status=is_active)
            
        # return queryset.order_by('transaction_date')

    # def get_queryset(self):
    #     queryset = super().get_queryset()
    #     params = self.request.query_params

    #     if branch := params.get('branch'):
    #         queryset = queryset.filter(branch__alias_id=branch)
    #     if date_from := params.get('transaction_date_after'):
    #         queryset = queryset.filter(transaction_date__gte=date_from)
    #     if date_to := params.get('transaction_date_before'):
    #         queryset = queryset.filter(transaction_date__lte=date_to)
    #     if customer := params.get('customer'):
    #         queryset = queryset.filter(customer__alias_id=customer)
    #     if status := params.get('status'):            
    #         # is_active = status.lower() == 'true'
    #         # queryset = queryset.filter(status=is_active)
    #         queryset = queryset.filter(status == 'true')
            
    #     return queryset.order_by('transaction_date')  # Now properly sorted

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