# Generated by Django 4.2.20 on 2025-04-16 19:39

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cheques', '0004_chequestore_insturment_type'),
    ]

    operations = [
        migrations.RenameField(
            model_name='chequestore',
            old_name='insturment_type',
            new_name='instrument_type',
        ),
    ]
