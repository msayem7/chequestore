from django.db import models, transaction
from rest_framework import serializers
from .models import (Branch, #ChequeStore, InvoiceChequeMap, 
                     Customer, CreditInvoice,) #MasterClaim, CustomerClaim, CustomerPayment, InvoiceClaimMap)
from .models import Payment, PaymentDetails, Customer, Branch, PaymentInstrument, PaymentInstrumentType, Claim

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404

from django.core.exceptions import ValidationError 

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email
        }
        return data

class BranchSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(
        slug_field='alias_id',
        queryset=Branch.objects.all(),
        required=False,
        allow_null=True
    )
    branch_type = serializers.IntegerField()
    
    class Meta:
        model = Branch
        fields = [
            'alias_id', 'name', 'parent', 'branch_type',
            'address', 'contact','updated_at', 'version'
        ]
        read_only_fields = ['alias_id', 'version']

        lookup_field = 'alias_id'

        extra_kwargs = {
            'url': {'lookup_field': 'alias_id'}
        }
   
#-----------------------------
class CustomerSerializer(serializers.ModelSerializer):
    branch = serializers.SlugRelatedField(
        slug_field='alias_id',
        queryset=Branch.objects.all(),
        required=True
    )
    parent = serializers.SlugRelatedField(
        slug_field='alias_id',
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True
    )
    parent_name = serializers.CharField(source='parent.name', read_only=True)
 

    is_active = serializers.BooleanField(
        required=False,  # Make field optional in requests
        default=True     # Set default for serializer validation
    )
    
    class Meta:
        model = Customer
        fields = ['alias_id', 'branch','name', 'is_parent', 'parent'
                  , 'parent_name','grace_days', 'address', 'phone','is_active', 'created_at', 'updated_at']
        read_only_fields = ['alias_id', 'created_at', 'updated_at']
    
    
        # extra_kwargs = {
        #     'parent': {'required': False}
        # }
class CreditInvoiceSerializer(serializers.ModelSerializer):
    alias_id = serializers.CharField(read_only=True) 

    branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
    customer = serializers.SlugRelatedField(slug_field='alias_id', queryset=Customer.objects.all())
    payment_grace_days = serializers.IntegerField(read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    status = serializers.BooleanField(default=True, required=False)
   

    payment = serializers.SlugRelatedField(slug_field='alias_id', required=False, allow_null=True, queryset=Payment.objects.all())
    
    
    net_due = serializers.DecimalField(
        max_digits=18, 
        decimal_places=4, 
        read_only=True
    )

    class Meta:
        model = CreditInvoice
        fields = ('alias_id', 'branch', 'grn', 'customer','customer_name', 'transaction_date'
                  ,'sales_amount','sales_return', 'net_due' ,'payment_grace_days', 'payment', 'status', 'version' #'allocated',
                  )
        read_only_fields = ('alias_id', 'version') #, 'updated_at', 'updated_by'
        optional_fields = ['payment']
    
       
    def create(self, validated_data):      
        claims_data = validated_data.pop('claims', [])
        validated_data['payment_grace_days'] = validated_data['customer'].grace_days
        instance = super().create(validated_data)
        # self._handle_claims(instance, claims_data)
        return instance
    
    def update(self, instance, validated_data):
        claims_data = validated_data.pop('claims', [])
        instance = super().update(instance, validated_data)
        # self._handle_claims(instance, claims_data)
        return instance


# class InvoiceChequeMapSerializer(serializers.ModelSerializer):
#     branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
#     credit_invoice = serializers.SlugRelatedField(slug_field='alias_id', queryset=CreditInvoice.objects.all())
#     cheque_store = serializers.SlugRelatedField(slug_field='receipt_no', queryset=ChequeStore.objects.all())
#     adjusted_date = serializers.DateField(default=timezone.now)  # Include adjusted_date in serializer

#     class Meta:
#         model = InvoiceChequeMap
#         fields = '__all__'

#  ---------------------implementing payment-----------------------

class PaymentInstrumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentInstrumentType
        fields = ['id','serial_no', 'type_name', 'is_cash_equivalent', 'prefix', 'last_number', 'auto_number' ]
        read_only_fields = ['id']

class PaymentInstrumentSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = PaymentInstrument
        fields = ['id', 'branch', 'serial_no','instrument_type','instrument_name', 'is_active','version']
        read_only_fields = ['version']

class PaymentDetailsSerializer(serializers.ModelSerializer):
    payment_instrument = serializers.PrimaryKeyRelatedField(
        queryset=PaymentInstrument.objects.all()
    )    

    instrument_type = serializers.IntegerField(
        source='payment_instrument.instrument_type.id',
        read_only=True
    )

    instrument_name = serializers.CharField(
        source='payment_instrument.instrument_name',
        read_only=True
    )

    id_number = serializers.CharField(  # Add explicit declaration
        max_length=10, 
        required=False, 
        allow_null=True, 
        allow_blank=True
    )

    class Meta:
        model = PaymentDetails
        fields = [
            'alias_id', 'id_number', 'payment_instrument', 'instrument_type', 
            'instrument_name', 'detail', 'amount'
        ]
        read_only_fields = [ 'alias_id', 'instrument_type', 'instrument_name']
        optional_fields = ['id_number', 'detail']
    
    def validate(self, attrs):
        payment_instrument = attrs.get('payment_instrument')
        if not payment_instrument:
            raise serializers.ValidationError({"payment_instrument": "This field is required."})
        
        instrument_type = payment_instrument.instrument_type
        if not instrument_type.auto_number and not attrs.get('id_number'):
            raise serializers.ValidationError(
                {"id_number": "ID number is required for manual entry instruments."}
            )
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    branch = serializers.SlugRelatedField(
        slug_field='alias_id',
        queryset=Branch.objects.all()
    )
    customer = serializers.SlugRelatedField(
        slug_field='alias_id',
        queryset=Customer.objects.filter(is_parent=True)
    )
    
    cash_equivalent_amount = serializers.DecimalField(
        max_digits=18, 
        decimal_places=4, 
        required=False, 
        default=0.0  # Default to 0.0 if not provided
    )

    claim_amount = serializers.DecimalField(
        max_digits=18, 
        decimal_places=4, 
        required=False, 
        default=0.0  # Default to 0.0 if not provided
    )

    total_amount = serializers.DecimalField(
        max_digits=18, 
        decimal_places=4, 
        required=False, 
        default=0.0  # Default to 0.0 if not provided
    )

    shortage_amount = serializers.DecimalField(
        max_digits=18, 
        decimal_places=4, 
        required=False, 
        default=0.0  # Default to 0.0 if not provided
    )

    payment_details = PaymentDetailsSerializer(many=True, source='paymentdetails_set')

    invoices = CreditInvoiceSerializer(many=True, required=True, source='invoice_set')

    
    class Meta:
        model = Payment
        fields = ['alias_id', 'branch', 'customer', 'received_date', 'cash_equivalent_amount',
                  'claim_amount','total_amount','shortage_amount', 'payment_details', 'invoices', 'version']
        read_only_fields = ['alias_id', 'version']
        
        extra_kwargs = {
            'alias_id': {'read_only': True}  # Explicitly make it read-only
        }
        
    def validate_customer(self, value):
        if not value.is_parent:
            raise serializers.ValidationError("Only parent customers allowed.")
        return value

# serializers.py
class ClaimListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='payment_details.payment.customer.name', read_only=True)
    instrument_name = serializers.CharField(source='payment_details.payment_instrument.instrument_name', read_only=True)
    claim_amount = serializers.DecimalField(
        source='payment_details.amount', 
        max_digits=18, 
        decimal_places=4, 
        read_only=True
    )
    claim_date = serializers.DateField(source='payment_details.payment.received_date', read_only=True)
    claim_serial_no = serializers.CharField(source='payment_details.id_number', read_only=True)
    detail = serializers.CharField(source='payment_details.detail', read_only=True)

    remaining_amount = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = [
            'alias_id', 'customer_name', 'instrument_name', 'claim_serial_no',
            'detail', 'claim_amount', 'claim_date', 'submitted_date',
            'refund_amount', 'refund_date', 'remarks', 'remaining_amount',
        ]

        read_only_fields = ['alias_id', 'customer_name', 'instrument_name', 'claim_amount', 
                            'claim_date', 'claim_serial_no', 'detail', ]
    def get_remaining_amount(self, obj):
        return obj.payment_details.amount - obj.refund_amount
    
class ClaimUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = ['submitted_date', 'refund_amount', 'refund_date', 'remarks']

    def validate(self, attrs):
        submitted_date = attrs.get('submitted_date')
        refund_amount = attrs.get('refund_amount')
        refund_date = attrs.get('refund_date')

        # Rule 1: If submitted_date is empty, refund_amount and refund_date are not allowed
        if submitted_date is None and (refund_amount or refund_date):
            raise ValidationError("Refund amount and refund date cannot be set unless the submitted date is provided.")
        
        # Rule 2: Refund amount and refund date pair: both must be provided or neither
        if (refund_amount is None and refund_date) or (refund_amount and refund_date is None):
            raise ValidationError("Refund amount and refund date must both be provided together.")
        
        return attrs
# class ClaimSerializer(serializers.ModelSerializer):    
#     branch = serializers.SlugRelatedField(
#         slug_field='alias_id',
#         queryset=Branch.objects.all()
#     )

#     class Meta:
#         model = Payment
#         fields = ['alias_id', 'branch', 'payment_details', 'submitted_date', 'refund_amount',
#                   'refund_date','remarks', 'version']
#         read_only_fields = ['alias_id', 'version']
#     def __str__(self):
#         return f"{self.payment_details.instrument_name}"


# class PaymentViewSerializer(serializers.ModelSerializer):
#     branch = serializers.SlugRelatedField(
#         slug_field='alias_id',
#         queryset=Branch.objects.all()
#     )
#     customer = serializers.SlugRelatedField(
#         slug_field='alias_id',
#         queryset=Customer.objects.filter(is_parent=True)
#     )
#     cash_equivalent = serializers.SerializerMethodField(
#         required=False,
#         allow_null=True
#     )
#     non_cash = serializers.SerializerMethodField(
#         required=False,
#         allow_null=True
#     )

#     payment_details = PaymentDetailsSerializer(many=True, source='paymentdetails_set')  # Changed to use reverse relation
    

#     class Meta:
#         model = Payment
#         fields = [
#             'alias_id', 'branch', 'customer', 'received_date', 'cash_equivalent', 'non_cash',
#             'payment_details','version'
#         ]
#         read_only_fields = ['alias_id', 'version']

#     def get_cash_equivalent(self, obj):
#         return obj.paymentdetails_set.filter(
#             payment_instrument__instrument_type=1
#         ).aggregate(total=models.Sum('amount'))['total'] or 0
    
    
    
#     def get_non_cash(self, obj):
#         return obj.paymentdetails_set.exclude(
#             payment_instrument__instrument_type=1
#         ).aggregate(total=models.Sum('amount'))['total'] or 0
    
    
#     def validate_customer(self, value):
#         if not value.is_parent:
#             raise serializers.ValidationError("Only parent customers allowed.")
#         return value

#  ----------------  implemented payment -----------------

  # Customer Statement
# class CustomerStatementSerializer(serializers.Serializer):
#     transaction_type_id = serializers.IntegerField()
#     transaction_type_name = serializers.CharField()
#     date = serializers.DateField()
#     particular = serializers.CharField()
#     sales_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
#     sales_return = serializers.DecimalField(max_digits=18, decimal_places=4)
#     net_sales = serializers.DecimalField(max_digits=18, decimal_places=4)
#     received = serializers.DecimalField(max_digits=18, decimal_places=4)
#     balance = serializers.DecimalField(max_digits=18, decimal_places=4)


# Parent Customer wise Due Report
# class ParentDueReportSerializer(serializers.Serializer):
#     parent_id = serializers.CharField()
#     parent_name = serializers.CharField()
#     net_sales = serializers.DecimalField(max_digits=18, decimal_places=4)
#     received = serializers.DecimalField(max_digits=18, decimal_places=4)
#     due = serializers.DecimalField(max_digits=18, decimal_places=4)
