from django import forms
from django.utils import timezone

from .models import EvenementSuivi, IncidentTransport, Transport


class EvenementSuiviForm(forms.ModelForm):
    date_evenement = forms.DateTimeField(
        label='Date et heure de l’événement',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'portal-input'}),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'],
    )

    class Meta:
        model = EvenementSuivi
        fields = ['statut', 'titre', 'lieu', 'description', 'date_evenement']
        labels = {
            'statut': 'Statut du transport',
            'titre': 'Titre de l’étape',
            'lieu': 'Lieu actuel',
            'description': 'Description / Observations',
            'date_evenement': 'Date et heure de l’événement',
        }
        widgets = {
            'titre': forms.TextInput(attrs={'placeholder': 'Ex. Prise en charge quai, Passage péage...', 'class': 'portal-input'}),
            'lieu': forms.TextInput(attrs={'placeholder': 'Ex. Tunis, Sousse, Sfax...', 'class': 'portal-input'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Observations complémentaires...', 'class': 'portal-input'}),
        }

    def __init__(self, *args, allowed_statuses=None, **kwargs):
        super().__init__(*args, **kwargs)
        if allowed_statuses is not None:
            self.fields['statut'].choices = [
                choice for choice in Transport.Statut.choices
                if choice[0] in allowed_statuses
            ]
        if not self.initial.get('date_evenement') and not self.data.get('date_evenement'):
            self.initial['date_evenement'] = timezone.localtime().strftime('%Y-%m-%dT%H:%M')
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'portal-input')


class IncidentTransportForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep the attachment optional even if model/form defaults change later.
        self.fields['photo'].required = False

    class Meta:
        model = IncidentTransport
        fields = ['categorie', 'description', 'priorite', 'photo']
        labels = {
            'categorie': 'Catégorie de l’incident',
            'description': 'Description',
            'priorite': 'Priorité',
            'photo': 'Photo (facultative)',
        }
        widgets = {
            'categorie': forms.Select(attrs={'class': 'portal-input'}),
            'description': forms.Textarea(attrs={
                'class': 'portal-input', 'rows': 3,
                'placeholder': 'Décrivez les faits, le lieu et les conséquences constatées…',
            }),
            'priorite': forms.Select(attrs={'class': 'portal-input'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'portal-input', 'accept': 'image/jpeg,image/png,image/webp'}),
        }

    def clean_description(self):
        description = self.cleaned_data['description'].strip()
        if len(description) < 10:
            raise forms.ValidationError('Ajoutez quelques précisions (10 caractères minimum).')
        return description


class TraitementIncidentForm(forms.Form):
    etat = forms.ChoiceField(
        label='État de résolution', choices=IncidentTransport.Etat.choices,
        widget=forms.Select(attrs={'class': 'admin-input'}),
    )
    commentaire = forms.CharField(
        label='Mise à jour pour le transporteur et la PME', required=False, max_length=1500,
        widget=forms.Textarea(attrs={
            'class': 'admin-input', 'rows': 4,
            'placeholder': 'Indiquez le traitement effectué ou la prochaine étape…',
        }),
    )
