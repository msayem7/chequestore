from django.db import models
from chequestore.inve_lib.inve_lib import generate_slugify_id, generate_alias_id
from django.contrib.auth.models import User
from django.utils import timezone
from PIL import Image

class Company(models.Model):
    alias_id = models.CharField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    company_name = models.TextField()
    email = models.EmailField(unique=True)
    mobile = models.TextField(null=False)
    version = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.company_name}"  # Use correct field name

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
    due_amount = models.DecimalField(max_digits=18, decimal_places=4)
    payment_grace_days = models.IntegerField(default=0)
    invoice_image = models.ImageField(upload_to='invoices/', null=True)
    status = models.BooleanField(default=True)  # this will be inactive
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    version = models.IntegerField(default=1)

    class Meta:
        verbose_name = 'Credit Invoice'
        verbose_name_plural = 'Credit Invoices'

    def __str__(self):
        return self.invoice_no +' - ' + self.customer.name +' - '+ str(self.due_amount)
    
    
class ChequeStore(models.Model):
    class ChequeStatus(models.IntegerChoices):
        RECEIVED = 1, 'Received'
        DEPOSITED = 2, 'Deposited'
        HONORED = 3, 'Honored'
        BOUNCED = 4, 'Bounced'    
    
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, blank=False, null=False)
    received_date = models.DateField(blank=False, null=False)
    cheque_image = models.ImageField(upload_to='cheque_images/', null=True, blank=False)
    cheque_date = models.DateField(null=True, blank=True)
    cheque_amount = models.DecimalField(max_digits=18, decimal_places=4)
    cheque_detail = models.TextField(null=False, blank=False, default='')
    cheque_status = models.IntegerField(choices=ChequeStatus.choices, default=ChequeStatus.RECEIVED)
    Notes = models.TextField(null=False, blank=False, default='')
    isActive = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL,null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'cheque_store'
        verbose_name = 'Cheque Store'
        verbose_name_plural = 'Cheque Stores'

    def __str__(self):
        return self.alias_id


class InvoiceChequeMap(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=False, null=False)
    creditinvoice = models.ForeignKey(CreditInvoice, on_delete=models.CASCADE)  # Fixed
    cheque_store = models.ForeignKey(ChequeStore, on_delete=models.CASCADE, related_name='invoice_cheques')
    adjusted_amount = models.DecimalField(max_digits=18, decimal_places=4)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete= models.SET_NULL, null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'invoice_cheque_map'
        verbose_name = 'Invoice Cheque Map'
        verbose_name_plural = 'Invoice Cheque Maps'

    def __str__(self):
        return str(self.creditinvoice + " : "+ self.cheque_store)

class ClaimCategory(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    category_name = models.TextField( blank=False, null=False) #name should be branch wise unique
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete= models.SET_NULL, null=True)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = 'Claim_Catatory'
        verbose_name = 'Claim Catatory'
        verbose_name_plural = 'Claim Catatories'
    
class MasterClaim(models.Model):
    class CategoryChoices(models.TextChoices):
        RETURN = 'SRTN', 'Sales Return'
        OTHER = 'OTH', 'Other Claims'

    
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    claim_name = models.TextField( blank=False, null=False) #name should be branch wise unique
    category = models.CharField(max_length=4, choices=CategoryChoices.choices, default=CategoryChoices.OTHER)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete= models.SET_NULL, null=True)
    version = models.IntegerField(default=1)
    class Meta:
        db_table = 'Master_Claim'
        verbose_name = 'Master Claim'
        verbose_name_plural = 'Master Claims'

    def __str__(self):
        return str(self.claim_name)
    
     
class CustomerClaim(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, blank=False, null=False)
    alias_id = models.TextField(default=generate_slugify_id, max_length=10, unique=True, editable=False)
    creditinvoice = models.ForeignKey(CreditInvoice, on_delete=models.PROTECT,  blank=False, null=False)  
    claim = models.ForeignKey(MasterClaim,on_delete=models.PROTECT, blank=False, null=False)
    claim_date = models.DateField( null=True)
    claim_amount = models.DecimalField( max_digits=18, decimal_places=4, null=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete= models.SET_NULL, null=True)
    version = models.IntegerField(default=1)
    class Meta:
        db_table = 'Customer_Claim'
        verbose_name = 'Customer Claim'
        verbose_name_plural = 'Customer Claims'

    def __str__(self):
        return str(self.creditinvoice.invoice_no + " : " + self.claim.claim_name + " : " + str(self.claim_amount))

        # return str(self.creditinvoice.invoice_no + " : " + self.claim.claim_name + " : "+ self.claim_amount)