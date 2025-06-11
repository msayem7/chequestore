from django.db import models
from rest_framework.exceptions import ValidationError
from src.inve_lib.inve_lib import generate_slugify_id, generate_alias_id
from django.contrib.auth.models import User
from django.utils import timezone
from PIL import Image

class BranchType(models.IntegerChoices):
    HEAD_OFFICE = 1, 'Head Office'
    BRANCH = 2, 'Branch'

class Branch(models.Model):
    alias_id = models.SlugField(
        max_length=10,
        unique=True,
        editable=False,
        default=generate_slugify_id
    )
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, 
                              null=True, blank=True, related_name='children')
    branch_type = models.IntegerField(choices=BranchType.choices, 
                                     default=BranchType.BRANCH)
    address = models.TextField(blank=True, null=True)
    contact = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT,
                                  null=True, blank=True)
    version = models.IntegerField(default=1)
    
    class Meta:
        db_table = 'branch'
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'

    def __str__(self):
        return f"{self.name}"


class Customer(models.Model):
    alias_id = models.TextField(
        max_length=10,
        unique=True,
        editable=False,
        default=generate_slugify_id
    ) 
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=True) 
    name = models.TextField()
    is_parent = models.BooleanField(default=False)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children' 
    )
    grace_days = models.IntegerField(default=0, null=True)
    address = models.TextField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active Status",
        help_text="Designates whether this customer should be treated as active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'customer'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'

    def __str__(self):
        return self.name



# Payment related changes
# class TestData(models.Model):
#     tab_test = models.TextField(blank=True, null=True)

class PaymentInstrumentType(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    serial_no = models.IntegerField(unique=False, null=False)
    type_name = models.TextField(blank=False, null=False) #name should be branch wise unique
    is_cash_equivalent = models.BooleanField(default=False) #True if it is cash equivalent
    prefix = models.CharField(max_length=2, null = False, blank=True)  # 2-character prefix -optional
    last_number = models.PositiveIntegerField(default=1)  # Last sequential number
    auto_number = models.BooleanField(default=False) #True if it is auto generated
    class Meta:
        db_table = 'payment_instrument_type'
        verbose_name = 'Payment Instrument Type'
        verbose_name_plural = 'Payment Instrument types'

    def __str__(self):
        return str(self.type_name)

class PaymentInstrument(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    serial_no = models.IntegerField( unique=False, null=False)
    instrument_type = models.ForeignKey(PaymentInstrumentType,on_delete=models.PROTECT,blank=False, null=False, related_name="payment_type") #name should be branch wise unique
    instrument_name = models.TextField(blank=False, null=False) #name should be branch wise unique
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete= models.SET_NULL, null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'payment_instrument'
        verbose_name = 'Payment Instrument'
        verbose_name_plural = 'Payment Instruments'

    def __str__(self):
        return str(self.instrument_name)

class Payment(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, blank=False, null=False)
    received_date = models.DateField(blank=False, null=False)
    claim_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)  
    cash_equivalent_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)
    total_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)
    shortage_amount= models.DecimalField(max_digits=18, decimal_places=4, default=0.0) 
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL,null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'payment'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'

    def __str__(self):
        return f"{self.received_date} - {self.customer.name}"
    
class PaymentDetails(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    id_number = models.CharField(max_length=10, blank=False, null=True)  # branch wise Unique identifier for the payment detail
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, blank=False, null=False)   
    payment_instrument = models.ForeignKey(PaymentInstrument, on_delete=models.CASCADE , blank=False, null=False) 
    detail= models.TextField(blank=True,null=True, default='')
    amount = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)
    # is_allocated = models.BooleanField(default=False)

    class Meta:
        db_table = 'payment_details'
        verbose_name = 'Payment Details'
        verbose_name_plural = 'Payments Details'
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'id_number'],
                name='unique_id_number'
            )
        ]

    def __str__(self):
        return f"{self.payment_instrument} - {self.detail}"

class CreditInvoice(models.Model):
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    grn = models.TextField(blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, blank=False, null=False)    
    transaction_date = models.DateField(blank=False, null=False)
    delivery_man = models.TextField(blank=True, null=True)
    transaction_details = models.TextField(blank=True, null=True)
    sales_amount = models.DecimalField(max_digits=18, decimal_places=4)
    sales_return = models.DecimalField(max_digits=18, decimal_places=4)
    payment_grace_days = models.IntegerField(default=0)
    invoice_image = models.ImageField(upload_to='invoices/', null=True)
    status = models.BooleanField(default=False)  #it is Payment_status, True = got payment , False= no payment 
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, blank=False, null=True,  related_name='invoice_set')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'credit_invoice'
        verbose_name = 'Credit Invoice'
        verbose_name_plural = 'Credit Invoices'

    def __str__(self):
        grn_display = self.grn or ''
        return f"{self.customer.name} - {self.sales_amount} -{self.grn}"


class Claim(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    payment_details = models.OneToOneField(PaymentDetails, on_delete=models.CASCADE, blank=False, null=False, related_name='payment_detail')
    submitted_date = models.DateField(blank=False, null=True)
    refund_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)
    refund_date = models.DateField(blank=False, null=True)
    remarks = models.TextField(blank= True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'claim'
        verbose_name = 'Claim'
        verbose_name_plural = 'Claims'

    def __str__(self):
        return f"Claim {self.alias_id} - {self.refund_amount} refunded"

    @property
    def is_fully_refunded(self):
        # The claim is fully refunded if the refund amount equals the claim amount
        return self.refund_amount == self.payment_details.amount

    def clean(self):
        if self.is_fully_refunded and self.refund_amount != self.payment_details.amount:
            raise ValidationError("Refund amount must be equal to the claim amount if fully refunded.")
        if not self.is_fully_refunded and self.refund_amount > self.payment_details.amount:
            raise ValidationError("Refund amount cannot exceed the claim amount unless fully refunded.")
        if self.refund_date < self.submitted_date:
            raise ValidationError("Refund date cannot be earlier than the submitted date.")
