from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ( CustomerViewSet
                    , BranchViewSet, CreditInvoiceViewSet
                    , MasterClaimViewSet
                    , CustomerClaimViewSet, CustomerPaymentViewSet
                    , CustomerStatementViewSet) # InvoiceChequeMapViewSet, ChequeStoreViewSet,


router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'branches', BranchViewSet)
router.register(r'credit-invoices', CreditInvoiceViewSet)
# router.register(r'cheques', ChequeStoreViewSet)
# router.register(r'invoice-cheques', InvoiceChequeMapViewSet)
router.register(r'master-claims', MasterClaimViewSet)
# router.register(r'claim-categories', ClaimCategoryViewSet)
router.register(r'customer-claims', CustomerClaimViewSet)
router.register(r'customer-payments', CustomerPaymentViewSet)
router.register(r'customer-statement', CustomerStatementViewSet, basename='customer-statement')



# urlpatterns = [
#     path('api/config/', frontend_config, name='frontend-config'),
# ]

urlpatterns = [
    path('', include(router.urls)),
]