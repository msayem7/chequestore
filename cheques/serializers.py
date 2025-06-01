from django.db import models, transaction
from rest_framework import serializers
from .models import (Branch, #ChequeStore, InvoiceChequeMap, 
                     Customer, CreditInvoice,) #MasterClaim, CustomerClaim, CustomerPayment, InvoiceClaimMap)
from .models import Payment, PaymentDetails, Customer, Branch, PaymentInstrument, PaymentInstrumentType

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
            'id_number', 'payment_instrument', 'instrument_type', 
            'instrument_name', 'detail', 'amount'
        ]
        read_only_fields = [ 'instrument_type', 'instrument_name']
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
    
    # def create(self, validated_data):
    #     # Extracting the nested fields
    #     payment_details_data = validated_data.pop('paymentdetails_set')
    #     invoices_data = validated_data.pop('invoice_set')  # Extract invoices data

    #     cash_equivalent_amount = validated_data.pop('cash_equivalent_amount', 0.0)
    #     claim_amount = validated_data.pop('claim_amount', 0.0)
    #     total_amount = validated_data.pop('total_amount', 0.0)
    #     shortage_amount = validated_data.pop('shortage_amount', 0.0)
        

    #     # Debugging the invoices_data right before processing
    #     print("Invoices Data before processing:", invoices_data)

    #     # Create the payment object
    #     payment = super().create(validated_data)

    #     errors = {}
    #     for index, detail_data in enumerate(payment_details_data):
    #         payment_instrument = detail_data['payment_instrument']
    #         instrument_type = payment_instrument.instrument_type

    #         if instrument_type.auto_number:
    #             locked_type = PaymentInstrumentType.objects.select_for_update().get(pk=instrument_type.id)
    #             locked_type.last_number += 1
    #             detail_data['id_number'] = f"{locked_type.prefix}{locked_type.last_number:04d}"
    #             locked_type.save()
    #         else:
    #             # Check uniqueness
    #             if PaymentDetails.objects.filter(branch=payment.branch, id_number=detail_data.get('id_number')).exists():
    #                 errors[f'payment_details.{index}.id_number'] = ["This ID number already exists in this branch."]

    #     if errors:
    #         raise serializers.ValidationError(errors)

    #     # Create payment details if no errors
    #     for detail_data in payment_details_data:
    #         PaymentDetails.objects.create(payment=payment, branch=payment.branch, **detail_data)

    #     # Iterate through the invoices and update them
    #     for invoice_data in invoices_data:
    #         # Ensure 'alias_id' is part of the invoice data
    #         invoice_alias_id = invoice_data.get('alias_id')
    #         if not invoice_alias_id:
    #             raise serializers.ValidationError("Missing 'alias_id' for one or more invoices")

    #         try:
    #             # Fetch the CreditInvoice model instance based on alias_id
    #             invoice = CreditInvoice.objects.get(alias_id=invoice_alias_id)

    #             # Assign the payment to the invoice
    #             invoice.payment = payment
    #             invoice.status = True  # Mark as paid
    #             invoice.save()
    #         except CreditInvoice.DoesNotExist:
    #             raise serializers.ValidationError(f"Invoice with alias_id {invoice_alias_id} does not exist.")

    #     payment.total_amount = total_amount
    #     payment.cash_equivalent_amount = cash_equivalent_amount
    #     payment.claim_amount = claim_amount
    #     payment.shortage_amount = shortage_amount
    #     payment.save() 

    #     return payment

    # def create(self, validated_data):
    #     # transaction stat at view
    #     # with transaction.atomic(): 
    #     payment_details_data = validated_data.pop('paymentdetails_set')
    #     shortage_amount = validated_data.pop('shortage_amount', 0.0)  # Default to 0.0 if not provided
    #     total_amount = validated_data.pop('total_amount', 0.0)  # Default to 0.0 if not provided
    #     cash_equivalent_amount = validated_data.pop('cash_equivalent_amount', 0.0)  # Default to 0.0 if not provided
    #     invoices_to_update = validated_data.pop('invoice_set')

    #     payment = super().create(validated_data)

    #     errors = {}
    #     for index, detail_data in enumerate(payment_details_data):
    #         payment_instrument = detail_data['payment_instrument']
    #         instrument_type = payment_instrument.instrument_type

    #         if instrument_type.auto_number:
    #             # Auto-number generation
    #             locked_type = PaymentInstrumentType.objects.select_for_update().get(pk=instrument_type.id)
    #             locked_type.last_number += 1
    #             detail_data['id_number'] = f"{locked_type.prefix}{locked_type.last_number:04d}"
    #             locked_type.save()
    #         else:
    #             # Check uniqueness
    #             if PaymentDetails.objects.filter(
    #                 branch=payment.branch, 
    #                 id_number=detail_data.get('id_number')
    #             ).exists():
    #                 errors[f'payment_details.{index}.id_number'] = [
    #                     "This ID number already exists in this branch."
    #                 ]

    #     if errors:
    #         raise serializers.ValidationError(errors)

    #     # Create payment details if no errors
    #     for detail_data in payment_details_data:
    #         PaymentDetails.objects.create(
    #             payment=payment,
    #             branch=payment.branch,
    #             **detail_data
    #         )

    #     for invoice_data in invoices_to_update:
    #         invoice = CreditInvoice.objects.get(alias_id=invoice_data['alias_id'])
    #         invoice.payment = payment  # Now, invoice is a proper model instance
    #         invoice.status = True
    #         invoice.save()

    #     payment.total_amount = total_amount
    #     payment.cash_equivalent_amount = cash_equivalent_amount
    #     # payment.claim_amount = payment_claim_amount
    #     payment.sortage_amount = shortage_amount
    #     payment.save()
        
        # return payment
    
    
        # ---------------------------------- invoices update -----------------------------
        
        # Sample list of invoices with their corresponding Payment objects
        # invoices_to_update = [
        #     {"invoice_alias_id": "e52138121c", "payment": payment_object_1},
        #     {"invoice_alias_id": "1c8af2e884", "payment": payment_object_2},
        # ]

        # invoices_to_update = validated_data.pop('invoices', [])
        # invoices_to_update is the list of updated credit invoices list 




        # # Step 1: Extract the alias_id_list
        # alias_id_list = [invoice["invoice_alias_id"] for invoice in invoices_to_update]
        # # Step 2: Perform the batch update using a transaction
        # with transaction.atomic():
        #     # for alias_id, payment_obj in payment_values.items():
        #         # Update the CreditInvoice record matching the alias_id and status=False
        #     CreditInvoice.objects.filter(
        #         alias_id__in=alias_id_list,
        #         payment__isnull=True  # Only update invoices with status=False (not paid yet)
        #     ).update(
        #         payment=payment,  # for different objects we can use invoice["payment"]
        #         status=True  # status object is not required. payment will replace it. 
        #     )

        # print("Batch update completed.")



        # -------------------update payment total amount -------------------



        # claim_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)  # Total claim amount
        # cash_equivalent_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)
        # total_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)
        # sortage_amount= models.DecimalField(max_digits=18, decimal_places=4, default=0.0) 


        # shortage_amount = validated_data.pop('shortage_amount', 0.0)  # Default to 0.0 if not provided
        # total_amount = validated_data.pop('total_amount', 0.0)  # Default to 0.0 if not provided
        # cash_equivalent_amount = validated_data.pop('cash_equivalent_amount', 0.0)  # Default to 0.0 if not provided


        # payment_claim_amount = payment.paymentdetails_set.filter(
        #     payment_instrument__instrument_type__is_cash_equivalent=False
        # ).aggregate(total=models.Sum('sales_amount')-models.Sum('sales_return'))['claim'] or 0
        
        # payment_cash_equivalent_amount = payment.paymentdetails_set.filter(
        #     payment_instrument_instrument_type_is_cash_equivalent=True
        # ).aggregate(total=models.Sum('sales_amount')-models.Sum('sales_return'))['cash_cheque'] or 0


        # payment_total_amount = payment.paymentdetails_set.filter(
        # ).aggregate(total=models.Sum('sales_amount')-models.Sum('sales_return'))['total'] or 0

        # if (payment_total_amount!=total_amount) or (payment_cash_equivalent_amount != cash_equivalent_amount) or (payment_claim_amount == claim_amount):
        #     raise serializers.ValidationError({
        #         'total_amount': "Total amount does not match with the sum of payment details."
        #     })
        
        
    def validate_customer(self, value):
        if not value.is_parent:
            raise serializers.ValidationError("Only parent customers allowed.")
        return value
        

class PaymentViewSerializer(serializers.ModelSerializer):
    branch = serializers.SlugRelatedField(
        slug_field='alias_id',
        queryset=Branch.objects.all()
    )
    customer = serializers.SlugRelatedField(
        slug_field='alias_id',
        queryset=Customer.objects.filter(is_parent=True)
    )
    cash_equivalent = serializers.SerializerMethodField(
        required=False,
        allow_null=True
    )
    non_cash = serializers.SerializerMethodField(
        required=False,
        allow_null=True
    )

    payment_details = PaymentDetailsSerializer(many=True, source='paymentdetails_set')  # Changed to use reverse relation
    

    class Meta:
        model = Payment
        fields = [
            'alias_id', 'branch', 'customer', 'received_date', 'cash_equivalent', 'non_cash',
            'payment_details','version'
        ]
        read_only_fields = ['alias_id', 'version']

    def get_cash_equivalent(self, obj):
        return obj.paymentdetails_set.filter(
            payment_instrument__instrument_type=1
        ).aggregate(total=models.Sum('amount'))['total'] or 0
    
    # def get_cash_equivalent(self, obj):
    #     # Sum amounts where payment instrument is cash equivalent
    #     result = obj.paymentdetails_set.filter(
    #         payment_instrument__instrument_type__is_cash_equialent=True
    #     ).aggregate(total=Sum('amount'))['total']

        # return result if result is not None else Decimal('0.0000')
    
    def get_non_cash(self, obj):
        return obj.paymentdetails_set.exclude(
            payment_instrument__instrument_type=1
        ).aggregate(total=models.Sum('amount'))['total'] or 0
    # def get_non_cash(self, obj):
    #     # Sum amounts where payment instrument is cash equivalent
    #     result = obj.paymentdetails_set.filter(
    #         payment_instrument__instrument_type__is_cash_equialent=False
    #     ).aggregate(total=Sum('amount'))['total']
        
    #     return result if result is not None else Decimal('0.0000')

    
    def validate_customer(self, value):
        if not value.is_parent:
            raise serializers.ValidationError("Only parent customers allowed.")
        return value

    # @transaction.atomic
    # def create(self, validated_data):
    #     payment_details_data = validated_data.pop('paymentdetails_set')
    #     validated_data['updated_by'] = self.context['request'].user
    #     payment = Payment.objects.create(**validated_data)

    #     # Create payment details - FIXED SYNTAX
    #     for detail_data in payment_details_data:
    #         PaymentDetails.objects.create(
    #             payment=payment,
    #             branch=payment.branch,  # Added comma here
    #             # updated_by=self.context['request'].user,  # Added missing field
    #             **detail_data
    #         )
    #     return payment


#  ----------------  implemented payment -----------------



# class MasterClaimSerializer(serializers.ModelSerializer):
    
#     branch = serializers.SlugRelatedField(
#         slug_field='alias_id',
#         queryset=Branch.objects.all(),
#         required=True
#     )
        
#     class Meta:
#         model = MasterClaim

#         fields = [
#             'alias_id', 'branch', 'claim_name', 'prefix', 'next_number', 'is_active'
#         ]
        # , 'updated_at', 'updated_by', 'version'

     
# class CustomerClaimSerializer(serializers.ModelSerializer):
#     claim = serializers.SlugRelatedField(
#         slug_field='alias_id', 
#         queryset=MasterClaim.objects.all()
#     )

#     class Meta:
#         model = CustomerClaim
#         fields = [
#            'claim_no', 'claim', 'claim_amount', 'details'
#         ]

# class ChequeStoreSerializer(serializers.ModelSerializer):
#     instrument_type = serializers.IntegerField(default=2)  # Default to Cheque (2)    
#     allocated = serializers.DecimalField(
#         max_digits=18, 
#         decimal_places=4, 
#         required=False,  # Make this field optional
#         read_only=True   # Let the server calculate this
#     )
    
#     class Meta:
#         model = ChequeStore
#         fields = [
#             'receipt_no', 'cheque_date', 'cheque_detail',
#             'cheque_amount', 'allocated', 'cheque_image', 'cheque_status',
#             'instrument_type'
#         ]

# class CustomerPaymentSerializer(serializers.ModelSerializer):
#     branch = serializers.SlugRelatedField(slug_field='alias_id', queryset=Branch.objects.all())
#     customer = serializers.SlugRelatedField(slug_field='alias_id', queryset=Customer.objects.all(), required=True)
#     cheques = ChequeStoreSerializer(many=True, required=False)
#     claims = CustomerClaimSerializer(many=True, required=False)
#     allocations = serializers.JSONField(write_only=True, required=False)


#     class Meta:
#         model = CustomerPayment
#         fields = (
#             'alias_id', 'branch', 'customer', 'received_date', 
#             'version', 'cheques', 'claims', 'allocations'
#         )
#         read_only_fields = ('alias_id', 'version', )

#     def validate(self, data):
#         # Check cheque uniqueness within the same branch
#         branch = data['branch']
        
#         for cheque_data in data.get('cheques', []):
#             if not cheque_data.get('receipt_no'):
#                 raise serializers.ValidationError("Receipt number is required for cheque instruments.")
            
        
#         for claim_data in data.get('claims', []):
#             if not claim_data.get('claim_no'):
#                 raise serializers.ValidationError("Claim number is required for claims.")
#             else:
#                 claim_data['claim_no'] = claim_data['claim_no'].strip()
#                 if not claim_data['claim_no']:
#                     raise serializers.ValidationError("Claim number is required.") 
        
#         receipt_nos = [ch['receipt_no'] for ch in data.get('cheques', [])]
#         claim_nos = [cl['claim_no'] for cl in data.get('claims', [])]
#         last_claim_nos = [cl['claim_no'].strip()[-6:]  for cl in data.get('claims', [])]

#         #claims = data.get('claims', [])
#         # claim_nos, last_claim_nos = (
#         #     zip(*[
#         #         (cl['claim_no'], cl['claim_no'].strip()[-6:])  # Fixed tuple parentheses
#         #         for cl in claims
#         #     ]) if claims else ([], [])
#         # )

#         #claim_nos, last_claim_nos = (zip(*[(cl['claim_no'], cl['claim_no'].strip()[-6:]) for cl in claims]) if claims else ([], []))
        
#         # update empty values to '0' in allocations
#         for key, inner_dict in data.get('allocations', {}).items():
#             for data_type, value_dict in inner_dict.items():
#                 for inner_key, value in value_dict.items():
#                     if value == '':
#                         data.get('allocations', {})[key][data_type][inner_key] = '0'
#         print(data.get('allocations', {}))

#         # 1. Validate positive allocations
#         for invoice_id, allocation in data.get('allocations', {}).items():
#             for amount in allocation.get('cheques', {}).values():                
#                 if Decimal(amount) < Decimal('0'):
#                     raise serializers.ValidationError(
#                         "Received allocations must be positive amounts"
#                     )
#             for amount in allocation.get('existing_payments', {}).values():
#                 if Decimal(amount) < Decimal('0'):
#                     raise serializers.ValidationError(
#                         "Existing received allocations must be positive amounts"
#                     )
#             for amount in allocation.get('claims', {}).values():
#                 if Decimal(amount) < Decimal('0'):
#                     raise serializers.ValidationError(
#                         "Claim allocations must be positive amounts"
#                     )
        
#          # 2. Validate unique cheque/claim numbers within current order
#         if len(receipt_nos) != len(set(receipt_nos)):
#             raise serializers.ValidationError(
#                 "Cheque numbers must be unique within this payment"
#             )

#         if len(claim_nos) != len(set(claim_nos)):
#             raise serializers.ValidationError(
#                 "Claim numbers must be unique within this payment"
#             )
        
#          # 3. Validate branch-wide uniqueness for claims
#         claim_qs = CustomerClaim.objects.filter(
#             branch=branch,
#             claim_no__in=claim_nos
#         )          
        
#         # Exclude existing claims if updating
#         if self.instance and self.instance.pk:
#             claim_qs = claim_qs.exclude(customer_payment=self.instance)

#         if claim_qs.exists():
#             existing = claim_qs.values_list('claim_no', flat=True)
#             raise serializers.ValidationError({
#                 'claims': f"Claim numbers {list(existing)} already exist in this branch"
#             })

#         # # Validate branch-wide uniqueness for cheques
#         # if ChequeStore.objects.filter(
#         #     branch=branch, 
#         #     receipt_no__in=receipt_nos
#         # ).exists():
#         #     raise serializers.ValidationError("Branch wise cheque number must be unique")  
        
#         # Validate branch-wide uniqueness for cheques
#         cheque_qs = ChequeStore.objects.filter(
#             branch=branch,
#             receipt_no__in=receipt_nos
#         )
        

#         if self.instance and self.instance.pk:
#             cheque_qs = cheque_qs.exclude(customer_payment=self.instance)

#         if cheque_qs.exists():
#             existing = cheque_qs.values_list('receipt_no', flat=True)
#             raise serializers.ValidationError({
#                 'receipts': f"Receipt numbers {list(existing)} already exist in this branch"
#             })
#         return data
   
    # def create(self, validated_data):
    #     cheques_data = validated_data.pop('cheques', [])
    #     claims_data = validated_data.pop('claims', [])
    #     allocations = validated_data.pop('allocations', {})
    #     payment = super().create(validated_data)
    #     user = self.context['request'].user

    #     # Adjusted date from CustomerPayment's received_date
    #     adjusted_date = payment.received_date

    #     branch = payment.branch
    #     print("validated_data", validated_data)
    #     print("claims_data", claims_data)

    #     # Create cheques
    #     for cheque_data in cheques_data:
    #         ChequeStore.objects.create(
    #             customer_payment=payment,
    #             branch=branch,
    #             cheque_status=ChequeStore.ChequeStatus.RECEIVED,
    #             instrument_type=cheque_data.get('instrument_type', 2),  # Default to Cheque (2)
    #             receipt_no=cheque_data['receipt_no'],
    #             cheque_date=cheque_data.get('cheque_date'),
    #             cheque_detail=cheque_data.get('cheque_detail', ''),
    #             cheque_amount=cheque_data['cheque_amount'],
    #             cheque_image=cheque_data.get('cheque_image')
    #         )


    #     # Create claims
    #     for claim_data in claims_data:
    #         # next_number = claim_data.claim_no.strip()[-6:]

    #         # def get_last_six_integer(input_str):
    #         #     trimmed = input_str.strip()
    #         #     last_six = trimmed[-6:] if len(trimmed) >= 6 else trimmed
    #         #     return int(last_six) if last_six.isdigit() else 0
            
    #         #update last claim numner in MasterClaim
    #         next_claim_no = claim_data['claim'].next_number +1 #int(claim_data['claim_no'].strip()[-6:]) + 1 #claim_data['claim_no'].strip()[-6:]
    #         alias_id = claim_data['claim'].alias_id
    #         # MasterClaim.objects.update(alias_id=alias_id, next_number=next_claim_no)
    #         master_claim_instance = MasterClaim.objects.get(alias_id=alias_id)  # Corrected variable name
    #         master_claim_instance.next_number = next_claim_no
    #         master_claim_instance.save()
            
    #         print ("claim_data:- ", claim_data)
    #         CustomerClaim.objects.create(
    #             customer_payment=payment,
    #             branch=branch,
    #             **claim_data
    #         )
            

    #     # Create allocations
    #     for invoice_id, allocation in allocations.items():
    #         invoice = CreditInvoice.objects.get(alias_id=invoice_id)
            
    #         # Cheque allocations
    #         for receipt_no, amount in allocation['cheques'].items():
    #             if (Decimal(amount)>0):
    #                 cheque = ChequeStore.objects.get(
    #                     receipt_no=receipt_no,
    #                     customer_payment=payment
    #                 )
    #                 InvoiceChequeMap.objects.create(
    #                     credit_invoice=invoice,  # Correct field name
    #                     cheque_store=cheque,
    #                     adjusted_amount=amount,
    #                     adjusted_date=adjusted_date,  # Set the adjusted date
    #                     branch=payment.branch
    #                 )
                

    #         for receipt_no, amount in allocation['existingPayments'].items():
    #             if (Decimal(amount)>0):
    #                 cheque = ChequeStore.objects.get(
    #                     receipt_no=receipt_no
    #                 )
    #                 InvoiceChequeMap.objects.create(
    #                     credit_invoice=invoice,  # Correct field name
    #                     cheque_store=cheque,
    #                     adjusted_amount=amount,
    #                     adjusted_date=adjusted_date,  # Set the adjusted date
    #                     branch=payment.branch
    #                 )
                
    #         # Claim allocations
    #         for claim_no, amount in allocation['claims'].items():
    #             if (Decimal(amount)>0):
    #                 claim = CustomerClaim.objects.get(
    #                     claim_no=claim_no,
    #                     customer_payment=payment
    #                 )
    #                 InvoiceClaimMap.objects.create(
    #                     credit_invoice=invoice,  # Correct field name
    #                     customer_claim=claim,
    #                     adjusted_amount=amount,
    #                     adjusted_date=adjusted_date,  # Set the adjusted date   
    #                     branch=payment.branch
    #                 )
        
    #     return payment

  
  # Customer Statement
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


# Parent Customer wise Due Report
class ParentDueReportSerializer(serializers.Serializer):
    parent_id = serializers.CharField()
    parent_name = serializers.CharField()
    net_sales = serializers.DecimalField(max_digits=18, decimal_places=4)
    received = serializers.DecimalField(max_digits=18, decimal_places=4)
    due = serializers.DecimalField(max_digits=18, decimal_places=4)

# hierarchy wise custoer due report

# class CustomerDueSerializer(serializers.Serializer):
#     alias_id = serializers.CharField(max_length=10)
#     parent_name = serializers.CharField(max_length=100)
#     matured_net_sales = serializers.DecimalField(max_digits=18, decimal_places=4)
#     immatured_net_sales = serializers.DecimalField(max_digits=18, decimal_places=4)
#     cash = serializers.DecimalField(max_digits=18, decimal_places=4)
#     claim = serializers.DecimalField(max_digits=18, decimal_places=4)
#     due = serializers.DecimalField(max_digits=18, decimal_places=4)
#     customerwise_breakdown = serializers.JSONField()
from .models import CreditInvoice #InvoiceChequeMap, InvoiceClaimMap, CustomerClaim,  ChequeStore
from rest_framework import serializers

class InvoicePaymentReportSerializer(serializers.Serializer):
    grn = serializers.CharField()
    transaction_date = serializers.DateField()
    customer = serializers.CharField()
    sales_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    sales_return = serializers.DecimalField(max_digits=18, decimal_places=4)
    net_sales = serializers.SerializerMethodField()
    total_allocated = serializers.DecimalField(max_digits=18, decimal_places=4)
    due_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    
    # Cheque information
    cheques = serializers.SerializerMethodField()
    # Claim information
    claims = serializers.SerializerMethodField()

    def get_net_sales(self, obj):
        return obj.sales_amount - obj.sales_return
    
    def get_cheques(self, obj):
        cheque_maps = InvoiceChequeMap.objects.filter(credit_invoice=obj).order_by('cheque_store__customer_payment__received_date')        
        return [
            {
                'received_date': map.cheque_store.customer_payment.received_date,
                'receipt_no': map.cheque_store.receipt_no,
                'instrument_type': map.cheque_store.get_instrument_type_display(),
                'adjusted_amount': map.adjusted_amount,
                'cheque_amount': map.cheque_store.cheque_amount,
                'cheque_status': map.cheque_store.get_cheque_status_display()
            }
            for map in cheque_maps
        ]

    def get_claims(self, obj):
        claim_maps = InvoiceClaimMap.objects.filter(credit_invoice=obj).order_by('customer_claim__customer_payment__received_date')
        return [
            {
                'received_date': map.customer_claim.customer_payment.received_date,
                'claim_no': map.customer_claim.claim_no,
                'claim_name': map.customer_claim.claim.claim_name,
                'adjusted_amount': map.adjusted_amount,
                'claim_amount': map.customer_claim.claim_amount
            }
            for map in claim_maps
        ]

#     # Report for Customer Payment
# class CustomerInvoiceSerializer(serializers.ModelSerializer):    
#     credit_invoice = CreditInvoiceSerializer()
#     invoice_claim_map = InvoiceClaimMap(many=True, required=False)
#     invoice_cheque_map = InvoiceChequeMapSerializer(many=True, required=False)

#     customer_name = serializers.CharField(source='customer.name', read_only=True)
#     transaction_date = serializers.DateField(read_only=True)
#     sales_amount = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
#     sales_return = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
#     net_sales = serializers.SerializerMethodField()
    
#     class Meta:
#         model = CreditInvoice
#         fields = ['alias_id', 'customer', 'customer_name', 'transaction_date', 'sales_amount', 'sales_return', 'net_sales']
#         read_only_fields = ['alias_id']

#     def get_net_sales(self, obj):
#         return obj.sales_amount - obj.sales_return


# class PaymentReportSerializer(serializers.Serializer):
#     Customer= CustomerSerializer()
#     CustomerInvoice= CreditInvoiceSerializer()
#     CustomerClaim= CustomerClaimSerializer()
#     Customercheque= ChequeStoreSerializer()

