from django.db import models, transaction
from rest_framework import serializers
from .models import (Branch, ChequeStore, InvoiceChequeMap, 
                     Customer, CreditInvoice, MasterClaim, CustomerClaim, CustomerPayment, InvoiceClaimMap)
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
    claims = serializers.JSONField(write_only=True, required=False)
    branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
    customer = serializers.SlugRelatedField(slug_field='alias_id', queryset=Customer.objects.all())
    payment_grace_days = serializers.IntegerField(read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    status = serializers.BooleanField(default=True, required=False)
    
    allocated = serializers.DecimalField(
        max_digits=18, 
        decimal_places=4, 
        read_only=True,
        source='total_allocated'
    )
    net_due = serializers.DecimalField(
        max_digits=18, 
        decimal_places=4, 
        read_only=True
    )

    class Meta:
        model = CreditInvoice
        fields = ('alias_id', 'branch', 'invoice_no', 'customer','customer_name', 'transaction_date'
                  ,'sales_amount','sales_return', 'allocated','net_due' ,'payment_grace_days', 'status', 'claims','version'
                  )
        read_only_fields = ('alias_id', 'version') #, 'updated_at', 'updated_by'
    
       
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


class InvoiceChequeMapSerializer(serializers.ModelSerializer):
    branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
    credit_invoice = serializers.SlugRelatedField(slug_field='alias_id', queryset=CreditInvoice.objects.all())
    cheque_store = serializers.SlugRelatedField(slug_field='cheque_no', queryset=ChequeStore.objects.all())
    
    class Meta:
        model = InvoiceChequeMap
        fields = '__all__'


class MasterClaimSerializer(serializers.ModelSerializer):
    
    branch = serializers.SlugRelatedField(
        slug_field='alias_id',
        queryset=Branch.objects.all(),
        required=True
    )
        
    class Meta:
        model = MasterClaim

        fields = [
            'alias_id', 'branch', 'claim_name', 'is_active'
        ]
        # , 'updated_at', 'updated_by', 'version'

     
class CustomerClaimSerializer(serializers.ModelSerializer):
    claim = serializers.SlugRelatedField(
        slug_field='alias_id', 
        queryset=MasterClaim.objects.all()
    )

    class Meta:
        model = CustomerClaim
        fields = [
           'claim_no', 'claim', 'claim_amount', 'details'
        ]

class ChequeStoreSerializer(serializers.ModelSerializer):
    instrument_type = serializers.IntegerField(default=2)  # Default to Cheque (2)

    class Meta:
        model = ChequeStore
        fields = [
            'cheque_no', 'cheque_date', 'cheque_detail',
            'cheque_amount', 'cheque_image', 'cheque_status',
            'instrument_type'
        ]

class CustomerPaymentSerializer(serializers.ModelSerializer):
    branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
    customer = serializers.SlugRelatedField(slug_field='alias_id', queryset=Customer.objects.all(), required=True)
    cheques = ChequeStoreSerializer(many=True, required=False)
    claims = CustomerClaimSerializer(many=True, required=False)
    allocations = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = CustomerPayment
        fields = (
            'alias_id', 'branch', 'customer', 'received_date', 
            'version', 'cheques', 'claims', 'allocations'
        )
        read_only_fields = ('alias_id', 'version', )

    def validate(self, data):
        # Check cheque uniqueness within the same branch
        branch = data['branch']
        
        for cheque_data in data.get('cheques', []):
            if not cheque_data.get('cheque_no'):
                raise serializers.ValidationError("Cheque number is required for cheque instruments.")
        
        cheque_nos = [ch['cheque_no'] for ch in data.get('cheques', [])]
        claim_nos = [cl['claim_no'] for cl in data.get('claims', [])]

        # 1. Validate positive allocations
        for invoice_id, allocation in data.get('allocations', {}).items():
            for amount in allocation.get('cheques', {}).values():
                if Decimal(amount) < Decimal('0'):
                    raise serializers.ValidationError(
                        "Cheque allocations must be positive amounts"
                    )
            for amount in allocation.get('claims', {}).values():
                if Decimal(amount) < Decimal('0'):
                    raise serializers.ValidationError(
                        "Claim allocations must be positive amounts"
                    )
        
         # 2. Validate unique cheque/claim numbers within current order
        if len(cheque_nos) != len(set(cheque_nos)):
            raise serializers.ValidationError(
                "Cheque numbers must be unique within this payment"
            )

        if len(claim_nos) != len(set(claim_nos)):
            raise serializers.ValidationError(
                "Claim numbers must be unique within this payment"
            )
        
         # 3. Validate branch-wide uniqueness for claims
        claim_qs = CustomerClaim.objects.filter(
            branch=branch,
            claim_no__in=claim_nos
        )          
        
        # Exclude existing claims if updating
        if self.instance and self.instance.pk:
            claim_qs = claim_qs.exclude(customer_payment=self.instance)

        if claim_qs.exists():
            existing = claim_qs.values_list('claim_no', flat=True)
            raise serializers.ValidationError({
                'claims': f"Claim numbers {list(existing)} already exist in this branch"
            })

        # # Validate branch-wide uniqueness for cheques
        # if ChequeStore.objects.filter(
        #     branch=branch, 
        #     cheque_no__in=cheque_nos
        # ).exists():
        #     raise serializers.ValidationError("Branch wise cheque number must be unique")  
        
        # Validate branch-wide uniqueness for cheques
        cheque_qs = ChequeStore.objects.filter(
            branch=branch,
            cheque_no__in=cheque_nos
        )

        if self.instance and self.instance.pk:
            cheque_qs = cheque_qs.exclude(customer_payment=self.instance)

        if cheque_qs.exists():
            existing = cheque_qs.values_list('cheque_no', flat=True)
            raise serializers.ValidationError({
                'cheques': f"Cheque numbers {list(existing)} already exist in this branch"
            })
        return data
   
    def create(self, validated_data):
        cheques_data = validated_data.pop('cheques', [])
        claims_data = validated_data.pop('claims', [])
        allocations = validated_data.pop('allocations', {})
        payment = super().create(validated_data)
        user = self.context['request'].user
        branch = payment.branch

        # Create cheques
        for cheque_data in cheques_data:
            ChequeStore.objects.create(
                customer_payment=payment,
                branch=branch,
                cheque_status=ChequeStore.ChequeStatus.RECEIVED,
                instrument_type=cheque_data.get('instrument_type', 2),  # Default to Cheque (2)
                cheque_no=cheque_data['cheque_no'],
                cheque_date=cheque_data.get('cheque_date'),
                cheque_detail=cheque_data.get('cheque_detail', ''),
                cheque_amount=cheque_data['cheque_amount'],
                cheque_image=cheque_data.get('cheque_image')               
            )

        # Create claims
        for claim_data in claims_data:
            CustomerClaim.objects.create(
                customer_payment=payment,
                branch=branch,
                **claim_data
            )

        # Create allocations
        for invoice_id, allocation in allocations.items():
            invoice = CreditInvoice.objects.get(alias_id=invoice_id)
            
            # Cheque allocations
            for cheque_no, amount in allocation['cheques'].items():
                cheque = ChequeStore.objects.get(
                    cheque_no=cheque_no,
                    customer_payment=payment
                )
                InvoiceChequeMap.objects.create(
                    credit_invoice=invoice,  # Correct field name
                    cheque_store=cheque,
                    adjusted_amount=amount,
                    branch=payment.branch
                )
                
            # Claim allocations
            for claim_no, amount in allocation['claims'].items():
                claim = CustomerClaim.objects.get(
                    claim_no=claim_no,
                    customer_payment=payment
                )
                InvoiceClaimMap.objects.create(
                    credit_invoice=invoice,  # Correct field name
                    customer_claim=claim,
                    adjusted_amount=amount,
                    branch=payment.branch
                )
        
        return payment

  
  # Add to serializers.py
class CustomerStatementSerializer(serializers.Serializer):
    transaction_type_id = serializers.IntegerField()
    transaction_type_name = serializers.CharField()
    date = serializers.DateField()
    particular = serializers.CharField()
    sales_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    sales_return = serializers.DecimalField(max_digits=18, decimal_places=4)
    net_sales = serializers.DecimalField(max_digits=18, decimal_places=4)
    received = serializers.DecimalField(max_digits=18, decimal_places=4)
    balance = serializers.DecimalField(max_digits=18, decimal_places=4)