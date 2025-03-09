from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (  ChequeStoreViewSet, CustomerViewSet
                    , BranchViewSet, CreditInvoiceViewSet
                    , InvoiceChequeMapViewSet, ClaimCategoryViewSet, MasterClaimViewSet
                    , CustomerClaimViewSet)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'branches', BranchViewSet)
router.register(r'credit-invoices', CreditInvoiceViewSet)
router.register(r'cheques', ChequeStoreViewSet)
router.register(r'invoice-cheques', InvoiceChequeMapViewSet)
router.register(r'master-claims', MasterClaimViewSet)
router.register(r'claim-categories', ClaimCategoryViewSet)
router.register(r'customer-claims', CustomerClaimViewSet)

urlpatterns = [
    path('', include(router.urls)),
]