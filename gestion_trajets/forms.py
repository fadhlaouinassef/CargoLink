from django import forms
from django.utils import timezone

from .models import OffreTransport, Trajet


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'portal-input'


class TrajetForm(StyledModelForm):
    class Meta:
        model = Trajet
        fields = ['depart_ville', 'arrivee_ville', 'date_depart', 'vehicule', 'capacite_kg', 'volume_m3', 'statut']
        widgets = {'date_depart': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})}

    def clean(self):
        data = super().clean()
        if data.get('depart_ville', '').casefold() == data.get('arrivee_ville', '').casefold():
            self.add_error('arrivee_ville', 'Choisissez une ville différente du départ.')
        date = data.get('date_depart')
        if date and date < timezone.now() and (not self.instance.pk or 'date_depart' in self.changed_data):
            self.add_error('date_depart', 'Le départ doit être dans le futur.')
        if self.instance.pk and self.instance.offres.filter(statut=OffreTransport.Statut.ACCEPTEE).exists():
            if set(self.changed_data) - {'statut'}:
                raise forms.ValidationError('Une offre est acceptée : seul le suivi de l’état du trajet peut être modifié.')
        return data


class SuiviForm(StyledModelForm):
    class Meta:
        model = Trajet
        fields = ['statut']


class OffreTransportForm(StyledModelForm):
    class Meta:
        model = OffreTransport
        fields = ['trajet', 'prix', 'message']
        widgets = {'message': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, transporteur, demande, **kwargs):
        super().__init__(*args, **kwargs)
        self.demande = demande
        self.fields['trajet'].queryset = Trajet.objects.filter(transporteur=transporteur, statut=Trajet.Statut.PUBLIE, date_depart__gte=timezone.now())
        self.fields['trajet'].empty_label = 'Choisir un de mes trajets publiés'

    def clean_trajet(self):
        trajet = self.cleaned_data['trajet']
        demande = self.demande
        if (trajet.depart_ville.casefold() != demande.depart_ville.casefold()
                or trajet.arrivee_ville.casefold() != demande.arrivee_ville.casefold()):
            raise forms.ValidationError('Le trajet doit relier les villes de cette demande.')
        date = timezone.localtime(trajet.date_depart).date()
        if not demande.date_depart <= date <= demande.date_limite:
            raise forms.ValidationError('Le départ doit respecter les dates de la demande.')
        goods = list(demande.marchandises.all())
        if sum(g.poids for g in goods) > trajet.capacite_kg:
            raise forms.ValidationError('La capacité du trajet est insuffisante.')
        if sum(g.volume or 0 for g in goods) > trajet.volume_m3:
            raise forms.ValidationError('Le volume du trajet est insuffisant.')
        return trajet
