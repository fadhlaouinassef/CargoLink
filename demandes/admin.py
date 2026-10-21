from django.contrib import admin
from django.contrib import messages

from .models import DemandeTransport, Marchandise


@admin.action(description='Masquer les demandes sélectionnées aux transporteurs')
def hide_demands(modeladmin, request, queryset):
    count = queryset.update(statut=DemandeTransport.Statut.MASQUEE)
    modeladmin.message_user(
        request,
        f'{count} demande(s) masquée(s) aux transporteurs.',
        messages.SUCCESS,
    )


@admin.action(description='Rendre visibles les demandes sélectionnées aux transporteurs')
def publish_demands(modeladmin, request, queryset):
    count = queryset.update(statut=DemandeTransport.Statut.OUVERTE)
    modeladmin.message_user(
        request,
        f'{count} demande(s) rendue(s) visibles aux transporteurs.',
        messages.SUCCESS,
    )


class MarchandiseInline(admin.TabularInline):
    model = Marchandise
    extra = 0


@admin.register(DemandeTransport)
class DemandeTransportAdmin(admin.ModelAdmin):
    list_display = ('id', 'depart_ville', 'arrivee_ville', 'statut', 'date_depart', 'created_at')
    list_filter = ('statut', 'date_depart')
    search_fields = ('depart_ville', 'arrivee_ville', 'destinataire_nom', 'created_by__email')
    inlines = (MarchandiseInline,)
    actions = (hide_demands, publish_demands)


@admin.register(Marchandise)
class MarchandiseAdmin(admin.ModelAdmin):
    list_display = ('description', 'type', 'poids', 'demande')
    list_filter = ('type', 'fragile')
    search_fields = ('description',)
