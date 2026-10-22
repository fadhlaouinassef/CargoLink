from django import forms

from .models import Disponibilite, Vehicule


class VehiculeForm(forms.ModelForm):
    class Meta:
        model = Vehicule
        fields = (
            'immatriculation',
            'marque',
            'modele',
            'annee',
            'type_vehicule',
            'capacite_poids_kg',
            'capacite_volume_m3',
            'statut',
            'photo',
        )
        widgets = {
            'annee': forms.NumberInput(attrs={'min': 1980}),
            'capacite_poids_kg': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
            'capacite_volume_m3': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
            'photo': forms.ClearableFileInput(attrs={'accept': '.jpg,.jpeg,.png,.webp'}),
        }
        labels = {
            'immatriculation': 'Immatriculation',
            'marque': 'Marque',
            'modele': 'Modèle',
            'annee': 'Année',
            'type_vehicule': 'Type de véhicule',
            'capacite_poids_kg': 'Capacité de poids (kg)',
            'capacite_volume_m3': 'Capacité de volume (m³)',
            'statut': 'Statut',
            'photo': 'Photo',
        }

    def clean_immatriculation(self):
        return self.cleaned_data['immatriculation'].strip().upper()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'portal-input')


class AdminVehiculeForm(VehiculeForm):
    class Meta(VehiculeForm.Meta):
        fields = ('transporteur',) + VehiculeForm.Meta.fields
        labels = {
            **VehiculeForm.Meta.labels,
            'transporteur': 'Transporteur propriétaire',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['transporteur'].queryset = self.fields['transporteur'].queryset.filter(
            role='transporteur',
        )


class DisponibiliteForm(forms.ModelForm):
    class Meta:
        model = Disponibilite
        fields = (
            'vehicule',
            'date_debut',
            'date_fin',
            'zone_depart',
            'zone_arrivee',
            'statut',
            'commentaire',
        )
        widgets = {
            'date_debut': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local'},
            ),
            'date_fin': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local'},
            ),
        }
        labels = {
            'vehicule': 'Véhicule',
            'date_debut': 'Date de début',
            'date_fin': 'Date de fin',
            'zone_depart': 'Zone de départ',
            'zone_arrivee': 'Zone d’arrivée',
            'statut': 'Statut',
            'commentaire': 'Commentaire',
        }

    def __init__(self, *args, transporteur=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'portal-input')
        if transporteur is not None:
            self.fields['vehicule'].queryset = Vehicule.objects.filter(
                transporteur=transporteur,
            ).exclude(
                statut__in=[Vehicule.Statut.EN_MAINTENANCE, Vehicule.Statut.DESACTIVE],
            )


class MaintenanceForm(forms.ModelForm):
    class Meta:
        from .models import Maintenance
        model = Maintenance
        fields = (
            'vehicule',
            'date_debut',
            'date_fin',
            'motif',
            'commentaire',
        )
        widgets = {
            'date_debut': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local'},
            ),
            'date_fin': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local'},
            ),
            'commentaire': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'vehicule': 'Véhicule',
            'date_debut': 'Date de début',
            'date_fin': 'Date de fin',
            'motif': 'Motif de la maintenance',
            'commentaire': 'Commentaire / Détails',
        }

    def __init__(self, *args, transporteur=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'portal-input')
        if transporteur is not None:
            self.fields['vehicule'].queryset = Vehicule.objects.filter(
                transporteur=transporteur,
            ).exclude(statut=Vehicule.Statut.DESACTIVE)


class AdminMaintenanceForm(MaintenanceForm):
    class Meta(MaintenanceForm.Meta):
        fields = ('vehicule', 'date_debut', 'date_fin', 'motif', 'statut', 'commentaire')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, transporteur=None, **kwargs)
        self.fields['vehicule'].queryset = Vehicule.objects.select_related('transporteur').all()

