# Generated by Django 5.1.6 on 2025-03-09 17:55

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheques', '0003_rename_catatory_name_claimcategory_category_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='masterclaim',
            name='claim_category',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, to='cheques.claimcategory'),
        ),
    ]
