# Generated by Django 5.1.6 on 2025-03-10 06:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheques', '0005_remove_masterclaim_claim_category_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='masterclaim',
            name='category',
            field=models.CharField(choices=[('SRTN', 'Sales Return'), ('OTH', 'Other Claims')], default='OTH', max_length=4),
        ),
    ]
