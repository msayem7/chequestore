# scripts/my_script.py
from cheques.models import *
from django.db.models import Sum, Prefetch, Value, F, Q,  OuterRef, Subquery, DecimalField
from django.db.models.functions import Coalesce
from datetime import date


def run():
    # Your ORM logic here
    branch_alias_id = '05f11f8870'
    branch = Branch.objects.get(alias_id=branch_alias_id)
    cutoff_date = date(2025, 12, 31)

    customers = Customer.objects.filter(is_parent=False, branch=branch).prefetch_related('parent')
    print customers.query
    
    parent_net_sales = Customer.objects.filter(
        branch=branch,
        is_parent=True,
        children__creditinvoice__transaction_date__lte=cutoff_date
    ).annotate(
        parent_net_sale=Sum(F('children__creditinvoice__sales_amount') - F('children__creditinvoice__sales_return'))
    ).values('alias_id', 'name', 'parent_net_sale')
    
    # print ("parent_net_sales: ", parent_net_sales.query)

    # for parent in parent_net_sales:
    #     print(f"Parent: {parent['name']} (ID: {parent['alias_id']})")
    #     print(f"Total Net Sales up to {cutoff_date}: {parent['parent_net_sale'] or 0}")
    

    parent_cash_received = Customer.objects.filter(
        branch=branch,
        is_parent=True,
        children__customerpayment__received_date__lte=cutoff_date
    ).annotate(
        received=Sum('children__customerpayment__chequestore__cheque_amount')
    ).values('alias_id', 'name', 'received')

    # print("parent_total_received SQL:", parent_cash_received.query)
    # for parent in parent_cash_received:
    #     print(f"{parent['name']} (ID: {parent['alias_id']}): Received {parent['received'] or 0}")


    parent_claim_received = Customer.objects.filter(
        branch=branch,
        is_parent=True,
        children__customerpayment__received_date__lte=cutoff_date
    ).annotate(
        received=Sum('children__customerpayment__customerclaim__claim_amount')
    ).values('alias_id', 'name', 'received')

    # print("parent_total_received SQL:", parent_claim_received.query)
    # for parent in parent_claim_received:
    #     print(f"{parent['name']} (ID: {parent['alias_id']}): Received {parent['received'] or 0}")



# New queeies

    parents = Customer.objects.filter(branch=branch, is_parent=True).values('alias_id', 'name')

    # 2. Get net sales per parent (sales_amount - sales_return)
    net_sales = (
        CreditInvoice.objects.filter(
            customer__parent__branch=branch,
            transaction_date__lte=cutoff_date
        ).values('customer__parent__alias_id', 'customer__parent__name')
        .annotate(Due=Sum(F('sales_amount') - F('sales_return')))
    )
    
    # 3. Get cash/cheque received per parent (only honored cheques)
    cash_received = (
        ChequeStore.objects.filter(
            customer_payment__customer__parent__branch=branch,
            customer_payment__received_date__lte=cutoff_date
        ).values('customer_payment__customer__parent__alias_id', 'customer_payment__customer__parent__name')
        .annotate(Due=Sum('cheque_amount')*-1)
    )
    
    # 4. Get claims received per parent
    claims_received = (
        CustomerClaim.objects.filter(
            customer_payment__customer__parent__branch=branch,
            customer_payment__received_date__lte=cutoff_date
        ).values('customer_payment__customer__parent__alias_id', 'customer_payment__customer__parent__name')
        .annotate(due=Sum('claim_amount')*-1)
    )
    


    # I want to calculate customer wise total due = parent_net_sales.parent_net_sale - parent_cash_received.received - parent_claim_received.received

    # Can i declare this 3 as subquery and then use it in the main query to get the final result?


    # # Subquery 1: Net Sales (sales_amount - sales_return)
    # net_sales_subquery = (
    #     CreditInvoice.objects.filter(
    #         customer__parent=OuterRef('pk'),
    #         transaction_date__lte=cutoff_date
    #     ).values('customer__parent')
    #     .annotate(total=Sum(F('sales_amount') - F('sales_return'), output_field=DecimalField()))
    #     .values('total')[:1]
    # )

    # # Subquery 2: Cash/Cheque Received
    # cash_received_subquery = (
    #     ChequeStore.objects.filter(
    #         customer_payment__customer__parent=OuterRef('pk'),
    #         customer_payment__received_date__lte=cutoff_date
    #     ).values('customer_payment__customer__parent')
    #     .annotate(total=Sum('cheque_amount', output_field=DecimalField()))
    #     .values('total')[:1]
    # )

    # # Subquery 3: Claims Received
    # claims_received_subquery = (
    #     CustomerClaim.objects.filter(
    #         customer_payment__customer__parent=OuterRef('pk'),
    #         customer_payment__received_date__lte=cutoff_date
    #     ).values('customer_payment__customer__parent')
    #     .annotate(total=Sum('claim_amount', output_field=DecimalField()))
    #     .values('total')[:1]
    # )

    # # Main Query with explicit output_field
    # parent_due_summary = (
    #     Customer.objects.filter(
    #         branch=branch,
    #         is_parent=True
    #     ).annotate(
    #         net_sales=Coalesce(Subquery(net_sales_subquery), 0.0, output_field=DecimalField()),
    #         cash_received=Coalesce(Subquery(cash_received_subquery), 0.0, output_field=DecimalField()),
    #         claims_received=Coalesce(Subquery(claims_received_subquery), 0.0, output_field=DecimalField()),
    #         total_due=F('net_sales') - F('cash_received') - F('claims_received')
    #     ).values(
    #         'alias_id',
    #         'name',
    #         'net_sales',
    #         'cash_received',
    #         'claims_received',
    #         'total_due'
    #     )
    # )

    # print("Parent Due Summary SQL:", parent_due_summary.query)
    # for parent in parent_due_summary:
    #     print(f"Parent: {parent['name']} (ID: {parent['alias_id']})")
    #     print(f"Net Sales: {parent['net_sales'] or 0}")
    #     print(f"Cash Received: {parent['cash_received'] or 0}")
    #     print(f"Claims Received: {parent['claims_received'] or 0}")
    #     print(f"Total Due: {parent['total_due'] or 0}")