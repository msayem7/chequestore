from django.db import models
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


class CreditInvoice(models.Model):
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    invoice_no = models.TextField(blank=False, null=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, blank=False, null=False)
    transaction_date = models.DateField(blank=False, null=False)
    delivery_man = models.TextField(blank=True, null=True)
    transaction_details = models.TextField(blank=True, null=True)
    sales_amount = models.DecimalField(max_digits=18, decimal_places=4)
    sales_return = models.DecimalField(max_digits=18, decimal_places=4)
    payment_grace_days = models.IntegerField(default=0)
    invoice_image = models.ImageField(upload_to='invoices/', null=True)
    status = models.BooleanField(default=True)  # True = Net sale amount is not fully adjusted, False= Fully adjusted
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'credit_invoice'
        verbose_name = 'Credit Invoice'
        verbose_name_plural = 'Credit Invoices'

    def __str__(self):
        return f"{self.invoice_no} - {self.customer.name} - {self.sales_amount}"
        # return self.invoice_no +' - ' + self.customer.name +' - '+ str(self.sales_amount)

class MasterClaim(models.Model):  
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    claim_name = models.TextField( blank=False, null=False) #name should be branch wise unique
    prefix = models.CharField(max_length=2, null = True)  # 2-character prefix
    next_number = models.PositiveIntegerField(default=1)  # Last sequential number
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete= models.SET_NULL, null=True)
    version = models.IntegerField(default=1)
    class Meta:
        db_table = 'master_claim'
        verbose_name = 'Master Claim'
        verbose_name_plural = 'Master Claims'

    def __str__(self):
        return str(self.claim_name)


class CustomerPayment(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, blank=False, null=False)
    received_date = models.DateField(blank=False, null=False)
    # isActive = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL,null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'customer_payment'
        verbose_name = 'Customer Payment'
        verbose_name_plural = 'Customer Payments'

    def __str__(self):
        return f"{self.received_date} - {self.customer.name}"

class ChequeStore(models.Model):   
    class ChequeStatus(models.IntegerChoices):
        RECEIVED = 1, 'Received'
        DEPOSITED = 2, 'Deposited'
        HONORED = 3, 'Honored'
        BOUNCED = 4, 'Bounced' 
    class instrument_type(models.IntegerChoices):
        CASH = 1, 'Cash'
        CHEQUE = 2, 'Cheque'
        PO = 3, 'Pay Order'
        EFT = 4, 'EFT'
        RTGS = 5, 'RTGS'
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    instrument_type = models.IntegerField(choices=instrument_type.choices, default=instrument_type.CHEQUE)
    receipt_no = models.TextField( max_length=10)
    customer_payment = models.ForeignKey(CustomerPayment, on_delete=models.PROTECT, blank=False, null=False)
    cheque_image = models.ImageField(upload_to='cheque_images/', null=True, blank=False)
    cheque_date = models.DateField(null=True, blank=True)
    cheque_amount = models.DecimalField(max_digits=18, decimal_places=4)
    cheque_detail = models.TextField(null=False, blank=True, default='')
    cheque_status = models.IntegerField(choices=ChequeStatus.choices, default=ChequeStatus.RECEIVED)

    class Meta:
        db_table = 'cheque_store'
        verbose_name = 'Cheque Store'
        verbose_name_plural = 'Cheque Stores'

    def __str__(self):
        return self.receipt_no

class InvoiceChequeMap(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    credit_invoice = models.ForeignKey(CreditInvoice, on_delete=models.CASCADE, related_name='cheque_allocations')  # Fixed
    cheque_store = models.ForeignKey(ChequeStore, on_delete=models.CASCADE, related_name='invoice_cheques')
    adjusted_amount = models.DecimalField(max_digits=18, decimal_places=4)
    adjusted_date = models.DateField(default=timezone.now)

    class Meta:
        db_table = 'invoice_cheque_map'
        verbose_name = 'Invoice Cheque Map'
        verbose_name_plural = 'Invoice Cheque Maps'

    def __str__(self):
        return f"{self.credit_invoice} : {self.cheque_store}"


class CustomerClaim(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    claim_no = models.TextField(max_length=10, editable=True)
    claim = models.ForeignKey(MasterClaim,on_delete=models.PROTECT, blank=False, null=False)
    customer_payment = models.ForeignKey(CustomerPayment, on_delete=models.PROTECT, blank=False, null=True)
    details = models.TextField( blank=True, null=True)
    claim_amount = models.DecimalField( max_digits=18, decimal_places=4, null=False)
    
    class Meta:
        db_table = 'customer_claim'
        verbose_name = 'Customer Claim'
        verbose_name_plural = 'Customer Claims'

    def __str__(self):
        return str(self.creditinvoice.invoice_no + " : " + self.claim.claim_name + " : " + str(self.claim_amount))

class InvoiceClaimMap(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    credit_invoice = models.ForeignKey(CreditInvoice, on_delete=models.PROTECT, related_name='claim_allocations')  # Fixed
    customer_claim = models.ForeignKey(CustomerClaim, on_delete=models.PROTECT,  blank=False, null=False, related_name='invoice_claim')
    adjusted_amount = models.DecimalField(max_digits=18, decimal_places=4)
    adjusted_date = models.DateField(default=timezone.now)

    class Meta:
        db_table = 'invoice_claim_map'
        verbose_name = 'Invoice claim Map'
        verbose_name_plural = 'Invoice Claim Maps'

    def __str__(self):
        return str(self.creditinvoice + " : "+ self.cheque_store)
