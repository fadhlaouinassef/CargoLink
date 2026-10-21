from django import forms
from django.core.validators import RegexValidator
from django.forms import inlineformset_factory

from .models import DemandeTransport, Marchandise


class DemandeTransportForm(forms.ModelForm):
    destinataire_tel = forms.CharField(
        label='Téléphone du destinataire',
        min_length=8,
        max_length=15,
        validators=[
            RegexValidator(
                regex=r'\A[0-9]+\Z',
                message='Saisissez uniquement des chiffres, sans espace ni indicatif +.',
            ),
        ],
        widget=forms.TextInput(attrs={
            'class': 'portal-input',
            'inputmode': 'numeric',
            'pattern': '[0-9]{8,15}',
            'autocomplete': 'tel-national',
            'maxlength': '15',
            'data-digits-only': 'true',
        }),
    )

    class Meta:
        model = DemandeTransport
        fields = (
            'depart_ville',
            'depart_adresse',
            'date_depart',
            'arrivee_ville',
            'arrivee_adresse',
            'date_limite',
            'destinataire_nom',
            'destinataire_contact',
            'destinataire_tel',
            'hayon',
            'transpalette',
            'bache',
            'consignes',
            'budget',
            'modalite_paiement',
            'validite_offres',
        )
        labels = {
            'depart_ville': 'Ville de départ',
            'depart_adresse': "Adresse d'enlèvement",
            'date_depart': "Date d'enlèvement souhaitée",
            'arrivee_ville': 'Ville de destination',
            'arrivee_adresse': 'Adresse de livraison',
            'date_limite': 'Date limite de réception',
            'destinataire_nom': 'Entreprise ou personne destinataire',
            'destinataire_contact': 'Responsable de réception',
            'destinataire_tel': 'Téléphone du destinataire',
            'hayon': 'Hayon élévateur requis',
            'transpalette': 'Transpalette à bord',
            'bache': 'Camion bâché / fermé',
            'consignes': 'Consignes particulières',
            'budget': 'Budget indicatif (TND)',
            'modalite_paiement': 'Modalité de règlement',
            'validite_offres': "Durée d'ouverture aux propositions",
        }
        widgets = {
            'depart_ville': forms.TextInput(attrs={'class': 'portal-input', 'placeholder': 'Ex. Tunis'}),
            'depart_adresse': forms.TextInput(attrs={'class': 'portal-input'}),
            'date_depart': forms.DateInput(attrs={'class': 'portal-input', 'type': 'date'}),
            'arrivee_ville': forms.TextInput(attrs={'class': 'portal-input', 'placeholder': 'Ex. Sfax'}),
            'arrivee_adresse': forms.TextInput(attrs={'class': 'portal-input'}),
            'date_limite': forms.DateInput(attrs={'class': 'portal-input', 'type': 'date'}),
            'destinataire_nom': forms.TextInput(attrs={'class': 'portal-input'}),
            'destinataire_contact': forms.TextInput(attrs={'class': 'portal-input'}),
            'hayon': forms.CheckboxInput(),
            'transpalette': forms.CheckboxInput(),
            'bache': forms.CheckboxInput(),
            'consignes': forms.Textarea(attrs={'class': 'portal-textarea', 'rows': 3}),
            'budget': forms.NumberInput(attrs={'class': 'portal-input', 'step': '0.01', 'min': '0'}),
            'modalite_paiement': forms.Select(attrs={'class': 'portal-select'}),
            'validite_offres': forms.Select(
                choices=(('24h', '24 heures (urgent)'), ('48h', '48 heures'), ('72h', '3 jours')),
                attrs={'class': 'portal-select'},
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        date_depart = cleaned_data.get('date_depart')
        date_limite = cleaned_data.get('date_limite')
        if date_depart and date_limite and date_limite < date_depart:
            self.add_error('date_limite', 'La date de réception doit être égale ou postérieure à la date de départ.')
        return cleaned_data


class MarchandiseForm(forms.ModelForm):
    class Meta:
        model = Marchandise
        fields = ('description', 'type', 'poids', 'volume', 'fragile')
        labels = {
            'description': 'Description',
            'type': 'Conditionnement',
            'poids': 'Poids (kg)',
            'volume': 'Volume (m³)',
            'fragile': 'Fragile',
        }
        widgets = {
            'description': forms.TextInput(attrs={'class': 'portal-input', 'placeholder': 'Décrivez la marchandise'}),
            'type': forms.Select(attrs={'class': 'portal-select'}),
            'poids': forms.NumberInput(attrs={'class': 'portal-input', 'step': '0.01', 'min': '0.01'}),
            'volume': forms.NumberInput(attrs={'class': 'portal-input', 'step': '0.01', 'min': '0'}),
            'fragile': forms.CheckboxInput(),
        }


MarchandiseFormSet = inlineformset_factory(
    DemandeTransport,
    Marchandise,
    form=MarchandiseForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
    max_num=15,
    validate_max=True,
)
