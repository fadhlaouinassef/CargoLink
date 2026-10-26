# Generated for the transport incident workflow.
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import vehicules.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('suivi_transport', '0001_initial'),
        ('vehicules', '0003_maintenance_kilometrage_releve_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IncidentTransport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('categorie', models.CharField(choices=[('panne', 'Panne du véhicule'), ('accident', 'Accident'), ('marchandise', 'Marchandise endommagée ou manquante'), ('retard', 'Retard important'), ('securite', 'Sécurité'), ('autre', 'Autre')], max_length=20)),
                ('description', models.TextField(max_length=3000)),
                ('priorite', models.CharField(choices=[('basse', 'Basse'), ('normale', 'Normale'), ('haute', 'Haute'), ('urgente', 'Urgente')], default='normale', max_length=10)),
                ('photo', models.ImageField(blank=True, upload_to='incidents-transport/', validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp']), vehicules.models.validate_photo_size])),
                ('etat', models.CharField(choices=[('signale', 'Signalé'), ('en_cours', 'En cours de traitement'), ('resolu', 'Résolu')], default='signale', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('signale_par', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='incidents_transport_signales', to=settings.AUTH_USER_MODEL)),
                ('transport', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incidents', to='suivi_transport.transport')),
            ],
            options={
                'ordering': ['-created_at', '-pk'],
                'indexes': [
                    models.Index(fields=['etat', 'priorite', 'created_at'], name='incident_etat_prio_date_idx'),
                    models.Index(fields=['transport', 'etat'], name='incident_transport_etat_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='HistoriqueIncident',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('etat', models.CharField(choices=[('signale', 'Signalé'), ('en_cours', 'En cours de traitement'), ('resolu', 'Résolu')], max_length=12)),
                ('commentaire', models.CharField(blank=True, max_length=1500)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('auteur', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='historique_incidents_transport', to=settings.AUTH_USER_MODEL)),
                ('incident', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historique', to='suivi_transport.incidenttransport')),
            ],
            options={
                'verbose_name': 'historique d’incident',
                'verbose_name_plural': 'historiques d’incidents',
                'ordering': ['created_at', 'pk'],
            },
        ),
    ]
