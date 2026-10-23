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
            'kilometrage',
            'date_releve_km',
            'photo',
        )
        widgets = {
            'annee': forms.NumberInput(attrs={'min': 1980}),
            'capacite_poids_kg': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
            'capacite_volume_m3': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
            'kilometrage': forms.NumberInput(attrs={'min': 0, 'placeholder': 'Ex: 125000'}),
            'date_releve_km': forms.DateInput(attrs={'type': 'date'}),
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
            'kilometrage': 'Kilométrage actuel (km)',
            'date_releve_km': 'Date du relevé kilométrique',
            'photo': 'Photo',
        }
        help_texts = {
            'kilometrage': 'Optionnel. Utilisé pour l’analyse indicative du risque de maintenance.',
            'date_releve_km': 'Optionnel. Date à laquelle ce relevé a été constaté.',
        }

    def clean_immatriculation(self):
        return self.cleaned_data['immatriculation'].strip().upper()

    def clean_kilometrage(self):
        km = self.cleaned_data.get('kilometrage')
        if km is not None and km < 0:
            raise forms.ValidationError('Le kilométrage doit être positif ou nul.')
        return km

    def clean(self):
        cleaned_data = super().clean()
        km = cleaned_data.get('kilometrage')
        # Avertissement non bloquant si km inférieur au relevé précédent
        if km is not None and self.instance and self.instance.pk and self.instance.kilometrage is not None:
            if km < self.instance.kilometrage:
                # Warning non bloquant via help_text ou message d'avertissement
                self.has_km_regression_warning = True
                self.km_previous_val = self.instance.kilometrage
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_km_regression_warning = False
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
            'kilometrage_releve',
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
            'kilometrage_releve': forms.NumberInput(attrs={'min': 0, 'placeholder': 'Ex: 126500'}),
            'commentaire': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'vehicule': 'Véhicule',
            'date_debut': 'Date de début',
            'date_fin': 'Date de fin',
            'motif': 'Motif de la maintenance',
            'kilometrage_releve': 'Kilométrage relevé (km)',
            'commentaire': 'Commentaire / Détails',
        }
        help_texts = {
            'kilometrage_releve': 'Optionnel. Relevé au compteur lors de cette maintenance.',
        }

    def clean_kilometrage_releve(self):
        km = self.cleaned_data.get('kilometrage_releve')
        if km is not None and km < 0:
            raise forms.ValidationError('Le kilométrage doit être positif ou nul.')
        return km

    def clean(self):
        cleaned_data = super().clean()
        km = cleaned_data.get('kilometrage_releve')
        vehicule = cleaned_data.get('vehicule') or (self.instance.vehicule if self.instance and self.instance.pk else None)
        if km is not None and vehicule and vehicule.kilometrage is not None:
            if km < vehicule.kilometrage:
                self.has_km_regression_warning = True
                self.km_previous_val = vehicule.kilometrage
        return cleaned_data

    def __init__(self, *args, transporteur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_km_regression_warning = False
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'portal-input')
        if transporteur is not None:
            self.fields['vehicule'].queryset = Vehicule.objects.filter(
                transporteur=transporteur,
            ).exclude(statut=Vehicule.Statut.DESACTIVE)


class AdminMaintenanceForm(MaintenanceForm):
    class Meta(MaintenanceForm.Meta):
        fields = ('vehicule', 'date_debut', 'date_fin', 'motif', 'statut', 'kilometrage_releve', 'commentaire')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, transporteur=None, **kwargs)
        self.fields['vehicule'].queryset = Vehicule.objects.select_related('transporteur').all()

