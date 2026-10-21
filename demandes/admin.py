from django.contrib import admin

from .models import DemandeTransport, Marchandise


class MarchandiseInline(admin.TabularInline):
    model = Marchandise
    extra = 0


@admin.register(DemandeTransport)
class DemandeTransportAdmin(admin.ModelAdmin):
    list_display = ('id', 'depart_ville', 'arrivee_ville', 'statut', 'date_depart', 'created_at')
    list_filter = ('statut', 'date_depart')
    search_fields = ('depart_ville', 'arrivee_ville', 'destinataire_nom')
    inlines = (MarchandiseInline,)


@admin.register(Marchandise)
class MarchandiseAdmin(admin.ModelAdmin):
    list_display = ('description', 'type', 'poids', 'demande')
    list_filter = ('type', 'fragile')
    search_fields = ('description',)
