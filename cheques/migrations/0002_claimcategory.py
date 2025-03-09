# Generated by Django 5.1.6 on 2025-03-09 09:10

import chequestore.inve_lib.inve_lib
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheques', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ClaimCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias_id', models.TextField(default=chequestore.inve_lib.inve_lib.generate_slugify_id, editable=False, max_length=10, unique=True)),
                ('catatory_name', models.TextField()),
                ('is_active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cheques.branch')),
                ('updated_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Claim Catatory',
                'verbose_name_plural': 'Claim Catatories',
                'db_table': 'Claim_Catatory',
            },
        ),
    ]
