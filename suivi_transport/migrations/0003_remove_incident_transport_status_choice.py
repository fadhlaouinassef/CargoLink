from django.db import migrations, models


TRANSPORT_STATUS_CHOICES = [
    ('planifie', 'Planifié'),
    ('pris_en_charge', 'Pris en charge'),
    ('en_transit', 'En transit'),
    ('arrive', 'Arrivé à destination'),
    ('livre', 'Livré'),
    ('annule', 'Annulé'),
]


class Migration(migrations.Migration):
    dependencies = [
        ('suivi_transport', '0002_incidenttransport_historiqueincident'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transport',
            name='statut',
            field=models.CharField(choices=TRANSPORT_STATUS_CHOICES, default='planifie', max_length=20),
        ),
        migrations.AlterField(
            model_name='evenementsuivi',
            name='statut',
            field=models.CharField(choices=TRANSPORT_STATUS_CHOICES, max_length=20),
        ),
    ]
