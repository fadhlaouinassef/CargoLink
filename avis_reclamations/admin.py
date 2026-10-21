from django.contrib import admin

from .models import Avis, Reclamation


@admin.register(Avis)
class AvisAdmin(admin.ModelAdmin):
    list_display = ('id', 'auteur', 'transporteur', 'note', 'statut', 'created_at')
    list_filter = ('statut', 'note')
    search_fields = ('auteur__full_name', 'transporteur__full_name', 'commentaire')


@admin.register(Reclamation)
class ReclamationAdmin(admin.ModelAdmin):
    list_display = ('reference', 'auteur', 'motif', 'statut', 'created_at')
    list_filter = ('statut', 'motif')
    search_fields = ('auteur__full_name', 'description')
