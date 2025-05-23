# Generated by Django 4.2.20 on 2025-04-14 13:14

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import src.inve_lib.inve_lib


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Branch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias_id', models.SlugField(default=src.inve_lib.inve_lib.generate_slugify_id, editable=False, max_length=10, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('branch_type', models.IntegerField(choices=[(1, 'Head Office'), (2, 'Branch')], default=2)),
                ('address', models.TextField(blank=True, null=True)),
                ('contact', models.TextField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='cheques.branch')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Branch',
                'verbose_name_plural': 'Branches',
                'db_table': 'branch',
            },
        ),
        migrations.CreateModel(
            name='ChequeStore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cheque_no', models.TextField(max_length=10)),
                ('cheque_image', models.ImageField(null=True, upload_to='cheque_images/')),
                ('cheque_date', models.DateField(blank=True, null=True)),
                ('cheque_amount', models.DecimalField(decimal_places=4, max_digits=18)),
                ('cheque_detail', models.TextField(blank=True, default='')),
                ('cheque_status', models.IntegerField(choices=[(1, 'Received'), (2, 'Deposited'), (3, 'Honored'), (4, 'Bounced')], default=1)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.branch')),
            ],
            options={
                'verbose_name': 'Cheque Store',
                'verbose_name_plural': 'Cheque Stores',
                'db_table': 'cheque_store',
            },
        ),
        migrations.CreateModel(
            name='CreditInvoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias_id', models.TextField(default=src.inve_lib.inve_lib.generate_slugify_id, editable=False, max_length=10, unique=True)),
                ('invoice_no', models.TextField()),
                ('transaction_date', models.DateField()),
                ('delivery_man', models.TextField(blank=True, null=True)),
                ('transaction_details', models.TextField(blank=True, null=True)),
                ('sales_amount', models.DecimalField(decimal_places=4, max_digits=18)),
                ('sales_return', models.DecimalField(decimal_places=4, max_digits=18)),
                ('payment_grace_days', models.IntegerField(default=0)),
                ('invoice_image', models.ImageField(null=True, upload_to='invoices/')),
                ('status', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='cheques.branch')),
            ],
            options={
                'verbose_name': 'Credit Invoice',
                'verbose_name_plural': 'Credit Invoices',
                'db_table': 'credit_invoice',
            },
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias_id', models.TextField(default=src.inve_lib.inve_lib.generate_slugify_id, editable=False, max_length=10, unique=True)),
                ('name', models.TextField()),
                ('is_parent', models.BooleanField(default=False)),
                ('grace_days', models.IntegerField(default=0, null=True)),
                ('address', models.TextField(blank=True, null=True)),
                ('phone', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this customer should be treated as active', verbose_name='Active Status')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('branch', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='cheques.branch')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='cheques.customer')),
            ],
            options={
                'verbose_name': 'Customer',
                'verbose_name_plural': 'Customers',
                'db_table': 'customer',
            },
        ),
        migrations.CreateModel(
            name='CustomerClaim',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('claim_no', models.TextField(max_length=10)),
                ('details', models.TextField(blank=True, null=True)),
                ('claim_amount', models.DecimalField(decimal_places=4, max_digits=18)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.branch')),
            ],
            options={
                'verbose_name': 'Customer Claim',
                'verbose_name_plural': 'Customer Claims',
                'db_table': 'customer_claim',
            },
        ),
        migrations.CreateModel(
            name='MasterClaim',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias_id', models.TextField(default=src.inve_lib.inve_lib.generate_slugify_id, editable=False, max_length=10, unique=True)),
                ('claim_name', models.TextField()),
                ('is_active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.branch')),
                ('updated_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Master Claim',
                'verbose_name_plural': 'Master Claims',
                'db_table': 'Master_Claim',
            },
        ),
        migrations.CreateModel(
            name='InvoiceClaimMap',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('adjusted_amount', models.DecimalField(decimal_places=4, max_digits=18)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.branch')),
                ('credit_invoice', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.creditinvoice')),
                ('customer_claim', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invoice_claim', to='cheques.customerclaim')),
            ],
            options={
                'verbose_name': 'Invoice claim Map',
                'verbose_name_plural': 'Invoice Claim Maps',
                'db_table': 'invoice_claim_map',
            },
        ),
        migrations.CreateModel(
            name='InvoiceChequeMap',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('adjusted_amount', models.DecimalField(decimal_places=4, max_digits=18)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='cheques.branch')),
                ('cheque_store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoice_cheques', to='cheques.chequestore')),
                ('credit_invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cheque_allocations', to='cheques.creditinvoice')),
            ],
            options={
                'verbose_name': 'Invoice Cheque Map',
                'verbose_name_plural': 'Invoice Cheque Maps',
                'db_table': 'invoice_cheque_map',
            },
        ),
        migrations.CreateModel(
            name='CustomerPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias_id', models.TextField(default=src.inve_lib.inve_lib.generate_slugify_id, editable=False, max_length=10, unique=True)),
                ('received_date', models.DateField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='cheques.branch')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.customer')),
                ('updated_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Customer Payment',
                'verbose_name_plural': 'Customer Payments',
                'db_table': 'customer_payment',
            },
        ),
        migrations.AddField(
            model_name='customerclaim',
            name='claim',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.masterclaim'),
        ),
        migrations.AddField(
            model_name='customerclaim',
            name='customer_payment',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='cheques.customerpayment'),
        ),
        migrations.AddField(
            model_name='creditinvoice',
            name='customer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.customer'),
        ),
        migrations.AddField(
            model_name='creditinvoice',
            name='updated_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='chequestore',
            name='customer_payment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.customerpayment'),
        ),
    ]
