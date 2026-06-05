# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('management', '0009_publicationresultats_decisionjury'),
    ]

    operations = [
        migrations.AddField(
            model_name='centralisationclasse',
            name='feedback_proviseur',
            field=models.TextField(blank=True, default='', verbose_name='Retour du proviseur'),
        ),
        migrations.AddField(
            model_name='centralisationclasse',
            name='date_validation',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Date de validation'),
        ),
    ]
