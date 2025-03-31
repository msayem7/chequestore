from django.db import models, transaction
from rest_framework import serializers
from .models import (Company, Branch, ChequeStore, InvoiceChequeMap, 
                     Customer, CreditInvoice, MasterClaim, CustomerClaim, CustomerPayment)
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
    
class CompanySerializer(serializers.ModelSerializer):
    alias_id = serializers.CharField(read_only=True)

    class Meta:
        model = Company
        fields = ['alias_id','company_name', 'email','mobile']
        # fields = '__all__'


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
    

    class Meta:
        model = CreditInvoice
        fields = ('alias_id', 'branch', 'invoice_no', 'customer','customer_name', 'transaction_date'
                  ,'sales_amount','sales_return' ,'payment_grace_days', 'status', 'claims','version'
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
    
    # def _handle_claims(self, instance, claims_data):
    #     with transaction.atomic():
    #         #This line retrieves all related CustomerClaim objects associated with the instance
    #         existing_claims = instance.customerclaim_set.all() 
    #         existing_claims_map = {str(c.alias_id): c for c in existing_claims}
    #         # for claim in existing_claims:
    #         #     print(f"existing_claims Alias ID: {claim.alias_id}, Claim Amount: {claim.claim_amount}, Version: {claim.version}")
    #         # Process claims
    #         seen_claims = set()
    #         for claim in claims_data:
    #             if not claim['existing']:
    #                 claim_obj = get_object_or_404(MasterClaim, alias_id=claim['alias_id'])
                
    #             # Update existing or create new
    #             if claim.get('existing'):
    #                 # print("existing_claims_map.get(claim['alias_id'])", existing_claims_map.get(claim['alias_id']), " claim['alias_id'] ", claim['alias_id'])
    #                 customer_claim = existing_claims_map.get(claim['alias_id'])
    #                 if customer_claim:
    #                     customer_claim.claim_date=claim.get('claim_date', timezone.now().date())
    #                     customer_claim.claim_amount = claim.get('claim_amount',0)
    #                     customer_claim.version += 1
    #                     customer_claim.save()
    #                     seen_claims.add(str(customer_claim.alias_id))
    #             else:
    #                 CustomerClaim.objects.create(
    #                     creditinvoice=instance,
    #                     claim=claim_obj,
    #                     claim_date = claim.get('claim_date', timezone.now().date()), #claim['claim_date'],
    #                     claim_amount=claim['claim_amount'],
    #                     branch=instance.branch,
    #                     updated_by=self.context['request'].user,
    #                     version=1
    #                 )
            
    #         # Delete claims not present in submission
    #         for claim in existing_claims:
    #             if str(claim.alias_id) not in seen_claims:
    #                 claim.delete()


class InvoiceChequeMapSerializer(serializers.ModelSerializer):
    branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
    creditinvoice = serializers.SlugRelatedField(slug_field='alias_id', queryset=CreditInvoice.objects.all())
    cheque_store = serializers.SlugRelatedField(slug_field='alias_id', queryset=ChequeStore.objects.all())

    class Meta:
        model = InvoiceChequeMap
        fields = '__all__'
        read_only_fields = ('version', 'updated_at', 'updated_by')


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


# class CustomerClaimSerializer(serializers.ModelSerializer):
#     branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
#     # creditinvoice = serializers.SlugRelatedField(slug_field='alias_id', queryset=CreditInvoice.objects.all())
#     claim = serializers.SlugRelatedField(slug_field='alias_id', queryset=MasterClaim.objects.all())
#     claim_name = serializers.CharField(source='claim.claim_name', read_only=True)
#     claim_date =  serializers.DateField(format='%Y-%m-%d', input_formats=['%Y-%m-%d']) #, input_formats=['%d-%m-%Y']

#     class Meta:
#         model = CustomerClaim
#         fields = ['branch', 'claim_no', 'claim', 'claim_name', 'claim_amount', 'details'] #'creditinvoice',
       
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
    # branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
    # customer_payment = serializers.SlugRelatedField(slug_field='alias_id', queryset=CustomerPayment.objects.all(), required=False)

    class Meta:
        model = ChequeStore
        fields = [
            'cheque_no', 'cheque_date', 'cheque_detail',
            'cheque_amount', 'cheque_image', 'cheque_status'
        ]
    # class Meta:
    #     model = ChequeStore
    #     fields = '__all__'
    #     read_only_fields = ('alias_id', 'version', 'updated_at', 'updated_by')


class CustomerPaymentSerializer(serializers.ModelSerializer):
    branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
    customer = serializers.SlugRelatedField(slug_field='alias_id', queryset=Customer.objects.all())
    cheques = ChequeStoreSerializer(many=True, required=False)
    claims = CustomerClaimSerializer(many=True, required=False)

    class Meta:
        model = CustomerPayment
        fields = (
            'alias_id', 'branch', 'customer', 'received_date', 
            'version', 'cheques', 'claims'
        )
        read_only_fields = ('alias_id', 'version', )

    def validate(self, data):
        # Check cheque uniqueness
        branch = data['branch']
        cheque_nos = [ch['cheque_no'] for ch in data.get('cheques', [])]
        if ChequeStore.objects.filter(branch=branch, cheque_no__in=cheque_nos).exists():
            raise serializers.ValidationError("Cheque number must be unique per branch")

        # Check claim uniqueness
        claim_nos = [cl['claim_no'] for cl in data.get('claims', [])]
        if CustomerClaim.objects.filter(branch=branch, claim_no__in=claim_nos).exists():
            raise serializers.ValidationError("Claim number must be unique per branch")

        return data

    def create(self, validated_data):
        cheques_data = validated_data.pop('cheques', [])
        claims_data = validated_data.pop('claims', [])
        payment = super().create(validated_data)
        user = self.context['request'].user
        branch = payment.branch  # Get branch from parent payment

        # Create cheques with branch from parent
        for cheque_data in cheques_data:
            ChequeStore.objects.create(
                customer_payment=payment,
                branch=branch,  # Add branch here
                cheque_status=ChequeStore.ChequeStatus.RECEIVED,
                **cheque_data
            )

        # Create claims with branch from parent'updated_at', 'updated_by'
        for claim_data in claims_data:
            CustomerClaim.objects.create(
                customer_payment=payment,
                branch=branch,  # Add branch here
                **claim_data
            )

        return payment 
    

    
# class CustomerPaymentSerializer(serializers.ModelSerializer):
#     branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
#     customer = serializers.SlugRelatedField(slug_field='alias_id', queryset=Customer.objects.all())
#     cheques = ChequeStoreSerializer(many=True, required=False)
#     claims = CustomerClaimSerializer(many=True, required=False)

#     class Meta:
#         model = CustomerPayment
#         fields = ('branch', 'customer','received_date', 'version')
#         read_only_fields = ('alias_id', 'version', 'updated_at', 'updated_by')

#     @transaction.atomic
#     def create(self, validated_data):
#         cheques_data = validated_data.pop('cheques', [])
#         claims_data = validated_data.pop('claims', [])
#         payment = super().create(validated_data)
        
#         # Create cheques
#         for cheque_data in cheques_data:
#             ChequeStore.objects.create(
#                 customer_payment=payment,
#                 **cheque_data,
#                 updated_by=self.context['request'].user
#             )
        
#         # Create claims
#         for claim_data in claims_data:
#             CustomerClaim.objects.create(
#                 customer_payment=payment,
#                 **claim_data,
#                 updated_by=self.context['request'].user
#             )
        
#         return payment