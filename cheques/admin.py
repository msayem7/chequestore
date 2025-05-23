from django.contrib import admin

# Register your models here.
from .models import PaymentInstrumentType, PaymentInstrument

admin.site.register(PaymentInstrumentType)
admin.site.register(PaymentInstrument)