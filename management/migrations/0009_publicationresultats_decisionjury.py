# Generated manually

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('management', '0008_attribution_max_examen_attribution_max_tj'),
    ]

    operations = [
        migrations.CreateModel(
            name='PublicationResultats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('est_publiee', models.BooleanField(default=False, verbose_name='Résultats publiés')),
                ('date_publication', models.DateTimeField(blank=True, null=True)),
                ('publie_par', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='publications_resultats',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Publication des résultats',
                'verbose_name_plural': 'Publications des résultats',
            },
        ),
        migrations.CreateModel(
            name='DecisionJury',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('decision', models.CharField(
                    choices=[
                        ('EN_ATTENTE', 'En attente'),
                        ('ADMIS', 'Admis'),
                        ('AJOURNE', 'Ajourné'),
                        ('REDOUBLE', 'Redouble'),
                        ('EXCLU', 'Exclu'),
                    ],
                    default='EN_ATTENTE',
                    max_length=20,
                )),
                ('commentaire', models.TextField(blank=True, default='')),
                ('date_decision', models.DateTimeField(auto_now=True)),
                ('classe', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='decisions_jury',
                    to='management.classe',
                )),
                ('eleve', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='decisions_jury',
                    to='management.eleve',
                )),
            ],
            options={
                'verbose_name': 'Décision du jury',
                'verbose_name_plural': 'Décisions du jury',
                'unique_together': {('eleve', 'classe')},
            },
        ),
    ]
