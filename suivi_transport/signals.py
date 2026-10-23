from django.db.models.signals import post_save
from django.dispatch import receiver

from gestion_trajets_offres.models import OffreTransport

from .models import EvenementSuivi, Transport


@receiver(post_save, sender=OffreTransport, dispatch_uid='suivi_transport.create_for_accepted_offer')
def create_transport_for_accepted_offer(sender, instance, **kwargs):
    if instance.statut != OffreTransport.Statut.ACCEPTEE:
        return
    transport, created = Transport.objects.get_or_create(offre=instance)
    if created:
        EvenementSuivi.objects.create(
            transport=transport,
            statut=Transport.Statut.PLANIFIE,
            titre='Transport planifié',
            description='Offre acceptée et transport confirmé.',
            cree_par_id=None,
        )
