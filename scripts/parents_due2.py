from django.db.models import Sum, F, Subquery, OuterRef, DecimalField
from django.db.models.functions import Coalesce
from cheques.models import *
from django.db.models import Sum, Prefetch, Value, F, Q,  OuterRef, Subquery, DecimalField
from django.db.models.functions import Coalesce
from datetime import date

# from cheques.models import Customer, CustomerPayment, ChequeStore, CustomerClaim, CreditInvoice


def run():
  branch_alias_id = '05f11f8870'
  branch = Branch.objects.get(alias_id=branch_alias_id)
  cutoff_date = date(2025, 12, 31)
  # 1. Get all parent customers
  
  parent_org_dues = get_parent_org_dues(branch_id=2)
  for org in parent_org_dues:
    print(f"{org['parent_org_name']}: Net Sales={org['net_sales']}, Due={org['due']}")


def get_parent_org_dues(branch_id, end_date='2025-12-31'):
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
        'net_sales': 0,
        'cash': 0,
        'claim': 0,
        'due': 0
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
        cheque_data = next((item for item in cheque_received if item['customer_id'] == customer_id), {'received': 0})
        claim_data = next((item for item in claim_received if item['customer_id'] == customer_id), {'received': 0})
        invoice_data = next((item for item in invoice if item['customer_id'] == customer_id), {'net_sales': 0})
        
        # Calculate values
        net_sales = invoice_data.get('net_sales', 0) or 0
        cash = cheque_data.get('received', 0) or 0
        claim = claim_data.get('received', 0) or 0
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
    
    return results