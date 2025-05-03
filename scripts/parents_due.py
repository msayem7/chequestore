# scripts/my_script.py
from cheques.models import *
from django.db.models import Sum, Prefetch, Value, F, Q,  OuterRef, Subquery, DecimalField
from django.db.models.functions import Coalesce
from datetime import date

from itertools import groupby
from operator import itemgetter

def run():
  branch_alias_id = '05f11f8870'
  branch = Branch.objects.get(alias_id=branch_alias_id)
  cutoff_date = date(2025, 12, 31)
  
  #customers = Customer.objects.filter(is_parent=False, branch=branch).prefetch_related('parent')
  # 1. Get net sales (positive due)
  parents = Customer.objects.filter(branch=branch, is_parent=True).values('alias_id', 'name')

  net_sales_subquery = (
      CreditInvoice.objects.filter(
          customer__parent__branch=branch,
          transaction_date__lte=cutoff_date
      ).values('customer__parent__alias_id', 'customer__parent__name')
      .annotate(due=Sum(F('sales_amount') - F('sales_return')))
  )

  # 2. Get cash/cheque received (negative due)
  cash_received_subquery = (
      ChequeStore.objects.filter(
          customer_payment__customer__parent__branch=branch,
          customer_payment__received_date__lte=cutoff_date
      ).values(
          alias_id=F('customer_payment__customer__parent__alias_id'),
          name=F('customer_payment__customer__parent__name')
      ).annotate(due=Sum('cheque_amount') * -1)  # Negative for deduction
  )

  # 3. Get claims received (negative due)
  claims_received_subquery = (
      CustomerClaim.objects.filter(
          customer_payment__customer__parent__branch=branch,
          customer_payment__received_date__lte=cutoff_date
      ).values(
          alias_id=F('customer_payment__customer__parent__alias_id'),
          name=F('customer_payment__customer__parent__name')
      ).annotate(due=Sum('claim_amount') * -1)  # Negative for deduction
  )

  CusDue = parents.filter(
    alias_id__in=net_sales_subquery.values('customer__parent__alias_id')).select_related('due')

  print(CusDue)

#   # 4. Combine all three queries
#   combined = net_sales.union(cash_received, claims_received)

#   # 5. Aggregate by alias_id and name
#   final_result = []
#   for key, group in groupby(
#       sorted(combined, key=itemgetter('alias_id', 'name')),
#       key=itemgetter('alias_id', 'name')
#   ):
#       total_due = sum(item['due'] for item in group)
#       final_result.append({
#           'alias_id': key[0],
#           'name': key[1],
#           'due': total_due
#       })

  # # Print results
  # for item in final_result:
  #     print(f"Parent: {item['name']} (ID: {item['alias_id']}) | Due: {item['due']}")