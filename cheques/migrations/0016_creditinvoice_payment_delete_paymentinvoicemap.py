# Generated by Django 4.2.20 on 2025-05-29 18:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cheques', '0015_paymentinvoicemap_remove_payment_is_allocated_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditinvoice',
            name='payment',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='cheques.payment'),
        ),
        migrations.DeleteModel(
            name='PaymentInvoiceMap',
        ),
    ]
