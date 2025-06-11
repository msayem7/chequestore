from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ( CustomerViewSet
                    , BranchViewSet, CreditInvoiceViewSet,
                    ClaimViewSet)
                    #, MasterClaimViewSet
                    # , CustomerClaimViewSet
                    # , CustomerPaymentViewSet
                    # , CustomerStatementViewSet) # InvoiceChequeMapViewSet, ChequeStoreViewSet,

from .views import PaymentInstrumentTypeViewSet, PaymentInstrumentsViewSet, PaymentViewSet


router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'branches', BranchViewSet)
router.register(r'credit-invoices', CreditInvoiceViewSet)
# router.register(r'customer-statement', CustomerStatementViewSet, basename='customer-statement')
router.register(r'payment-instruments', PaymentInstrumentsViewSet, basename='payment-instruments')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'PaymentInstrumentType', PaymentInstrumentTypeViewSet, basename='PaymentInstrumentType')
router.register(r'claims', ClaimViewSet, basename='claim')

# 

# urlpatterns = [
#     path('api/config/', frontend_config, name='frontend-config'),
# ]

urlpatterns = [
    path('', include(router.urls)),
]