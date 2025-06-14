# Generated by Django 4.2.20 on 2025-05-26 02:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheques', '0009_paymentdetails_unique_branch_id'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='paymentdetails',
            options={'verbose_name': 'Payment Details', 'verbose_name_plural': 'Payments Details'},
        ),
        migrations.RemoveConstraint(
            model_name='paymentdetails',
            name='unique_branch_id',
        ),
        migrations.AlterField(
            model_name='paymentdetails',
            name='amount',
            field=models.DecimalField(decimal_places=4, default=0.0, max_digits=18),
        ),
        migrations.AlterField(
            model_name='paymentdetails',
            name='id_number',
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.AddConstraint(
            model_name='paymentdetails',
            constraint=models.UniqueConstraint(fields=('branch', 'id_number'), name='unique_id_number'),
        ),
    ]
