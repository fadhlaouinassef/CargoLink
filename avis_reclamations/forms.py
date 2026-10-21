from django import forms

from demandes.models import DemandeTransport

from . import services
from .models import (
    AVIS_COMMENTAIRE_MAX, AVIS_COMMENTAIRE_MIN, MOTIF_MODERATION_MAX, MOTIF_MODERATION_MIN,
    RECLAMATION_DESCRIPTION_MAX, RECLAMATION_DESCRIPTION_MIN, REPONSE_MAX, REPONSE_MIN,
    Avis, Reclamation,
)

MSG_MIN = 'Saisissez au moins %(limit_value)d caractères (actuellement %(show_value)d).'
MSG_MAX = 'Saisissez au plus %(limit_value)d caractères (actuellement %(show_value)d).'


def texte_long(label, minimum, maximum, **attrs):
    """Zone de texte avec contrôle de longueur et compteur de caractères côté navigateur."""
    return forms.CharField(
        label=label,
        min_length=minimum,
        max_length=maximum,
        error_messages={'required': 'Ce champ est obligatoire.', 'min_length': MSG_MIN, 'max_length': MSG_MAX},
        widget=forms.Textarea(attrs={
            'class': 'portal-textarea', 'rows': 5, 'minlength': minimum, 'maxlength': maximum,
            'data-counter': maximum, **attrs,
        }),
    )


class DemandeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, demande):
        return f'{demande} · {demande.depart_ville} ➔ {demande.arrivee_ville} ({demande.date_depart:%d/%m/%Y})'


class TransporteurChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, transporteur):
        return transporteur.full_name


class SignalerErreursMixin:
    """Marque les champs invalides pour que le navigateur et le CSS les mettent en évidence."""

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs['class'] = f"{widget.attrs.get('class', '')} is-invalid".strip()
                widget.attrs['aria-invalid'] = 'true'


class AvisForm(SignalerErreursMixin, forms.ModelForm):
    demande = DemandeChoiceField(
        label='Demande de transport',
        queryset=DemandeTransport.objects.none(),
        empty_label='Choisissez la demande concernée',
        widget=forms.Select(attrs={'class': 'portal-select'}),
        error_messages={
            'required': 'Choisissez la demande concernée.',
            'invalid_choice': 'Cette demande n’est pas disponible : elle est déjà évaluée ou ne vous appartient pas.',
        },
    )
    transporteur = TransporteurChoiceField(
        label='Transporteur évalué',
        queryset=services.transporteurs_actifs(),
        empty_label='Choisissez le transporteur',
        widget=forms.Select(attrs={'class': 'portal-select'}),
        error_messages={
            'required': 'Choisissez le transporteur à évaluer.',
            'invalid_choice': 'Ce transporteur n’existe pas ou n’est plus actif.',
        },
    )
    note = forms.TypedChoiceField(
        label='Note globale',
        choices=[(valeur, str(valeur)) for valeur in range(5, 0, -1)],
        coerce=int,
        widget=forms.RadioSelect,
        error_messages={'required': 'Attribuez une note de 1 à 5 étoiles.', 'invalid_choice': 'La note doit être comprise entre 1 et 5.'},
    )
    commentaire = texte_long(
        'Votre commentaire', AVIS_COMMENTAIRE_MIN, AVIS_COMMENTAIRE_MAX,
        placeholder='Ponctualité, soin des marchandises, communication…',
    )

    class Meta:
        model = Avis
        fields = ('demande', 'transporteur', 'note', 'commentaire')

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['demande'].queryset = services.demandes_du_pme(user).exclude(avis__auteur=user)

    def save(self, commit=True):
        avis = super().save(commit=False)
        avis.auteur = self.user
        if commit:
            avis.save()
        return avis


class ReclamationForm(SignalerErreursMixin, forms.ModelForm):
    demande = DemandeChoiceField(
        label='Demande de transport concernée',
        queryset=DemandeTransport.objects.none(),
        empty_label='Choisissez la demande concernée',
        widget=forms.Select(attrs={'class': 'portal-select'}),
        error_messages={
            'required': 'Choisissez la demande concernée.',
            'invalid_choice': 'Cette demande n’est pas disponible pour une réclamation.',
        },
    )
    transporteur = TransporteurChoiceField(
        label='Transporteur concerné (facultatif)',
        queryset=services.transporteurs_actifs(),
        required=False,
        empty_label='Je ne sais pas / non précisé',
        widget=forms.Select(attrs={'class': 'portal-select'}),
        error_messages={'invalid_choice': 'Ce transporteur n’existe pas ou n’est plus actif.'},
    )
    motif = forms.ChoiceField(
        label='Motif de la réclamation',
        choices=[('', 'Choisissez un motif'), *Reclamation.Motif.choices],
        widget=forms.Select(attrs={'class': 'portal-select'}),
        error_messages={'required': 'Choisissez le motif de la réclamation.', 'invalid_choice': 'Ce motif n’est pas valide.'},
    )
    description = texte_long(
        'Description des faits', RECLAMATION_DESCRIPTION_MIN, RECLAMATION_DESCRIPTION_MAX,
        placeholder='Que s’est-il passé ? Quand ? Quelles réserves avez-vous émises ?', rows=6,
    )
    montant_prejudice = forms.DecimalField(
        label='Préjudice estimé en TND (facultatif)',
        required=False,
        min_value=0,
        max_value=1000000,
        max_digits=10,
        decimal_places=2,
        error_messages={
            'invalid': 'Saisissez un montant valide, par exemple 250 ou 250.50.',
            'min_value': 'Le montant ne peut pas être négatif.',
            'max_value': 'Le montant ne peut pas dépasser 1 000 000 TND.',
            'max_digits': 'Ce montant est trop grand.',
            'max_decimal_places': 'Utilisez au plus 2 chiffres après la virgule.',
        },
        widget=forms.NumberInput(attrs={'class': 'portal-input', 'step': '0.01', 'min': '0', 'max': '1000000', 'inputmode': 'decimal'}),
    )

    class Meta:
        model = Reclamation
        fields = ('demande', 'transporteur', 'motif', 'description', 'montant_prejudice')

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['demande'].queryset = services.demandes_reclamables(user)

    def clean_demande(self):
        demande = self.cleaned_data['demande']
        en_cours = Reclamation.objects.filter(auteur=self.user, demande=demande).exclude(
            statut__in=[Reclamation.Statut.RESOLUE, Reclamation.Statut.REJETEE],
        )
        if en_cours.exists():
            raise forms.ValidationError('Une réclamation est déjà en cours pour cette demande. Attendez son traitement.')
        return demande

    def save(self, commit=True):
        reclamation = super().save(commit=False)
        reclamation.auteur = self.user
        if commit:
            reclamation.save()
        return reclamation


class TraitementReclamationForm(SignalerErreursMixin, forms.Form):
    """Décision de l'administrateur : nouveau statut et réponse adressée à l'auteur."""

    statut = forms.ChoiceField(
        label='Nouvelle décision',
        widget=forms.RadioSelect,
        error_messages={'required': 'Choisissez une décision.', 'invalid_choice': 'Cette décision n’est pas possible pour ce dossier.'},
    )
    reponse = forms.CharField(
        label='Réponse à l’auteur',
        required=False,
        min_length=REPONSE_MIN,
        max_length=REPONSE_MAX,
        error_messages={'min_length': MSG_MIN, 'max_length': MSG_MAX},
        widget=forms.Textarea(attrs={
            'class': 'portal-textarea', 'rows': 5, 'minlength': REPONSE_MIN, 'maxlength': REPONSE_MAX,
            'data-counter': REPONSE_MAX, 'placeholder': 'Explication de la décision, solution proposée…',
        }),
    )

    def __init__(self, *args, reclamation, **kwargs):
        super().__init__(*args, **kwargs)
        self.reclamation = reclamation
        self.fields['statut'].choices = reclamation.statuts_suivants()
        self.fields['reponse'].initial = reclamation.reponse_admin

    def clean(self):
        cleaned = super().clean()
        statut = cleaned.get('statut')
        clotures = (Reclamation.Statut.RESOLUE, Reclamation.Statut.REJETEE)
        if statut in clotures and not cleaned.get('reponse') and 'reponse' not in self.errors:
            self.add_error('reponse', 'Expliquez votre décision : une réponse est obligatoire pour clôturer le dossier.')
        return cleaned


class ModerationAvisForm(SignalerErreursMixin, forms.Form):
    """Masquer un avis (motif obligatoire) ou le republier."""

    ACTION_MASQUER = 'masquer'
    ACTION_PUBLIER = 'publier'

    action = forms.ChoiceField(choices=[(ACTION_MASQUER, 'Masquer'), (ACTION_PUBLIER, 'Republier')])
    motif = forms.CharField(
        label='Motif du masquage',
        required=False,
        min_length=MOTIF_MODERATION_MIN,
        max_length=MOTIF_MODERATION_MAX,
        error_messages={'min_length': MSG_MIN, 'max_length': MSG_MAX},
        widget=forms.TextInput(attrs={'class': 'portal-input', 'maxlength': MOTIF_MODERATION_MAX}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('action') == self.ACTION_MASQUER and not cleaned.get('motif') and 'motif' not in self.errors:
            self.add_error('motif', 'Indiquez le motif du masquage.')
        return cleaned
