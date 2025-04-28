from django.views.decorators.cache import never_cache

from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
#media serving to urls.py: 
from django.conf import settings
from django.conf.urls.static import static
from cheques.views import CustomTokenObtainPairView, user_detail, unallocated_payments  #, CIvsChequeReportView
# from cheques.views import frontend_config

urlpatterns = [
    path('admin/', admin.site.urls),
    path('v1/chq/', include('cheques.urls')),
    path('v1/chq/unallocated-payments/', unallocated_payments, name='unallocated-payments'),
    # path('v1/chq/reports/ci-vs-cheque/', CIvsChequeReportView.as_view({'get': 'list'}), name='ci-cheque-report'),
    # path('v1/chq/reports/ci-vs-cheque/export_pdf/', CIvsChequeReportView.as_view(actions={'get': 'export_pdf'}), name='ci-cheque-report-pdf'),
    # path('v1/chq/reports/ci-vs-cheque/export_excel/', CIvsChequeReportView.as_view(actions={'get': 'export_excel'}), name='ci-cheque-report-excel'),
    path('v1/chq/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('v1/chq/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('v1/chq/user/', user_detail, name='user_detail'),
    # path('api/config/', frontend_config, name='frontend-config'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)