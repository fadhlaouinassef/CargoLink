from django.contrib import admin, messages
from django.utils.html import format_html
from .models import AnalyseRisque, Disponibilite, Maintenance, Vehicule


class AnalyseRisqueInline(admin.TabularInline):
    model = AnalyseRisque
    extra = 0
    ordering = ('-date_analyse',)
    readonly_fields = ('date_analyse', 'niveau_badge', 'score', 'source', 'divergence', 'urgence')
    fields = ('date_analyse', 'niveau_badge', 'score', 'source', 'urgence', 'divergence')
    can_delete = False

    @admin.display(description='Niveau')
    def niveau_badge(self, obj):
        colors = {
            'faible': ('#dcfce7', '#166534'),
            'moyen': ('#fef3c7', '#92400e'),
            'eleve': ('#fee2e2', '#991b1b'),
        }
        bg, fg = colors.get(obj.niveau, ('#f1f5f9', '#475569'))
        return format_html(
            '<span style="background:{}; color:{}; padding:3px 8px; border-radius:4px; font-weight:600;">{}</span>',
            bg, fg, obj.get_niveau_display()
        )


class MaintenanceInline(admin.TabularInline):
    model = Maintenance
    extra = 0
    ordering = ('-date_debut',)


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
        'dernier_risque',
        'date_creation',
    )
    list_filter = ('type_vehicule', 'statut')
    search_fields = ('immatriculation', 'marque', 'modele', 'transporteur__email', 'transporteur__full_name')
    inlines = (DisponibiliteInline, MaintenanceInline, AnalyseRisqueInline)
    actions = (desactiver_vehicules, reactiver_vehicules)

    @admin.display(description='Risque indicatif')
    def dernier_risque(self, obj):
        derniere = obj.analyses_risque.order_by('-date_analyse').first()
        if not derniere:
            return format_html('<span style="color:#94a3b8;">Non analysé</span>')
        colors = {
            'faible': ('#dcfce7', '#166534'),
            'moyen': ('#fef3c7', '#92400e'),
            'eleve': ('#fee2e2', '#991b1b'),
        }
        bg, fg = colors.get(derniere.niveau, ('#f1f5f9', '#475569'))
        return format_html(
            '<span style="background:{}; color:{}; padding:3px 8px; border-radius:4px; font-weight:600;">{} ({}%)</span>',
            bg, fg, derniere.get_niveau_display(), derniere.score
        )


@admin.register(AnalyseRisque)
class AnalyseRisqueAdmin(admin.ModelAdmin):
    list_display = (
        'vehicule',
        'transporteur',
        'niveau_badge',
        'score',
        'source',
        'urgence',
        'divergence',
        'date_analyse',
    )
    list_filter = ('niveau', 'source', 'divergence', 'urgence', 'date_analyse')
    search_fields = (
        'vehicule__immatriculation',
        'vehicule__marque',
        'vehicule__transporteur__email',
        'recommandation',
    )
    readonly_fields = (
        'vehicule',
        'niveau',
        'score',
        'facteurs',
        'recommandation',
        'motif_suggere',
        'urgence',
        'source',
        'modele_utilise',
        'confiance',
        'divergence',
        'donnees_hash',
        'duree_ms',
        'date_analyse',
    )

    @admin.display(description='Transporteur')
    def transporteur(self, obj):
        return obj.vehicule.transporteur

    @admin.display(description='Niveau')
    def niveau_badge(self, obj):
        colors = {
            'faible': ('#dcfce7', '#166534'),
            'moyen': ('#fef3c7', '#92400e'),
            'eleve': ('#fee2e2', '#991b1b'),
        }
        bg, fg = colors.get(obj.niveau, ('#f1f5f9', '#475569'))
        return format_html(
            '<span style="background:{}; color:{}; padding:3px 8px; border-radius:4px; font-weight:600;">{}</span>',
            bg, fg, obj.get_niveau_display()
        )



@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display = (
        'vehicule',
        'transporteur',
        'motif',
        'statut',
        'date_debut',
        'date_fin',
        'date_creation',
    )
    list_filter = ('statut', 'motif', 'date_debut')
    search_fields = (
        'vehicule__immatriculation',
        'vehicule__marque',
        'vehicule__transporteur__email',
        'vehicule__transporteur__full_name',
        'commentaire',
    )
    readonly_fields = ('date_creation', 'transporteur')

    @admin.display(description='Transporteur')
    def transporteur(self, obj):
        return obj.vehicule.transporteur


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
