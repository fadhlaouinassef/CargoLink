from django import forms
from django.utils import timezone

from vehicules.models import Vehicule

from .models import OffreTransport, Trajet


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'portal-input'


class VehiculeSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            option['attrs']['data-capacite'] = str(value.instance.capacite_poids_kg)
            option['attrs']['data-volume'] = str(value.instance.capacite_volume_m3)
        return option


class TrajetForm(StyledModelForm):
    vehicule = forms.ModelChoiceField(
        label='Véhicule', queryset=Vehicule.objects.none(),
        to_field_name='immatriculation', widget=VehiculeSelect,
        empty_label='Choisir un de mes véhicules',
    )

    class Meta:
        model = Trajet
        fields = ['depart_ville', 'arrivee_ville', 'date_depart', 'vehicule', 'capacite_kg', 'volume_m3', 'statut']
        widgets = {'date_depart': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})}

    def __init__(self, *args, transporteur, **kwargs):
        super().__init__(*args, **kwargs)
        vehicules = Vehicule.objects.filter(transporteur=transporteur)
        self.fields['vehicule'].queryset = vehicules
        self.fields['vehicule'].widget.attrs['data-trajet-vehicule'] = ''
        selected = self.data.get(self.add_prefix('vehicule')) if self.is_bound else self.initial.get('vehicule')
        vehicule = vehicules.filter(immatriculation=selected).first() if selected else None
        for name, value in (
            ('capacite_kg', vehicule.capacite_poids_kg if vehicule else None),
            ('volume_m3', vehicule.capacite_volume_m3 if vehicule else None),
        ):
            self.fields[name].disabled = True
            self.fields[name].required = False
            self.initial[name] = value

    def clean(self):
        data = super().clean()
        vehicule = data.get('vehicule')
        if vehicule:
            data['vehicule'] = vehicule.immatriculation
            data['capacite_kg'] = vehicule.capacite_poids_kg
            data['volume_m3'] = vehicule.capacite_volume_m3
        if data.get('depart_ville', '').casefold() == data.get('arrivee_ville', '').casefold():
            self.add_error('arrivee_ville', 'Choisissez une ville différente du départ.')
        date = data.get('date_depart')
        if date and date < timezone.now() and (not self.instance.pk or 'date_depart' in self.changed_data):
            self.add_error('date_depart', 'Le départ doit être dans le futur.')
        if self.instance.pk and self.instance.offres.filter(statut=OffreTransport.Statut.ACCEPTEE).exists():
            if (set(self.changed_data) - {'statut'}
                    or any(data.get(name) != getattr(self.instance, name) for name in ('capacite_kg', 'volume_m3'))):
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
