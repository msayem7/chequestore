# Generated by Django 5.1.6 on 2025-03-10 06:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheques', '0004_masterclaim_claim_category'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='masterclaim',
            name='claim_category',
        ),
        migrations.AddField(
            model_name='masterclaim',
            name='category',
            field=models.CharField(choices=[('DISC', 'Discounts'), ('OTH', 'Other Claims')], default='OTH', max_length=4),
        ),
    ]
