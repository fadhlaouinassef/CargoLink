from django.contrib import admin, messages
from .models import Disponibilite, Vehicule


class DisponibiliteInline(admin.TabularInline):
    model = Disponibilite
    extra = 0
    ordering = ('date_debut',)


@admin.action(description='Désactiver les véhicules sélectionnés')
def desactiver_vehicules(modeladmin, request, queryset):
    updated = queryset.exclude(statut=Vehicule.Statut.DESACTIVE).update(
        statut=Vehicule.Statut.DESACTIVE,
    )
    modeladmin.message_user(request, f'{updated} véhicule(s) désactivé(s).', messages.SUCCESS)


@admin.action(description='Réactiver les véhicules sélectionnés')
def reactiver_vehicules(modeladmin, request, queryset):
    updated = queryset.exclude(statut=Vehicule.Statut.ACTIF).update(
        statut=Vehicule.Statut.ACTIF,
    )
    modeladmin.message_user(request, f'{updated} véhicule(s) réactivé(s).', messages.SUCCESS)


@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    list_display = (
        'immatriculation',
        'transporteur',
        'marque',
        'modele',
        'type_vehicule',
        'statut',
        'date_creation',
    )
    list_filter = ('type_vehicule', 'statut')
    search_fields = ('immatriculation', 'marque', 'modele', 'transporteur__email', 'transporteur__full_name')
    readonly_fields = ('date_creation',)
    inlines = (DisponibiliteInline,)
    actions = (desactiver_vehicules, reactiver_vehicules)


@admin.register(Disponibilite)
class DisponibiliteAdmin(admin.ModelAdmin):
    list_display = (
        'vehicule',
        'transporteur',
        'date_debut',
        'date_fin',
        'zone_depart',
        'zone_arrivee',
        'statut',
    )
    list_filter = ('statut', 'date_debut')
    search_fields = (
        'vehicule__immatriculation',
        'vehicule__transporteur__email',
        'zone_depart',
        'zone_arrivee',
    )
    readonly_fields = ('transporteur',)

    @admin.display(description='Transporteur')
    def transporteur(self, obj):
        return obj.vehicule.transporteur

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
