# Generated by Django 5.1.6 on 2025-03-10 13:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheques', '0006_alter_masterclaim_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerclaim',
            name='claim_date',
            field=models.DateTimeField(null=True),
        ),
    ]
