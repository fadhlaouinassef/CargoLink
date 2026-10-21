from django.urls import include, path
from django.views.generic import TemplateView

from demandes import views as demande_views

app_name = 'transporteur'

urlpatterns = [
    path('demandes/', demande_views.transporteur_demandes, name='demandes'),
    path('demandes/<int:pk>/', demande_views.transporteur_demande_detail, name='demande_detail'),
    path('', include('avis_reclamations.urls_transporteur')),
] + [
    path(route, TemplateView.as_view(template_name=f'transporteur/{name}.html', extra_context={'active_tab': name}), name=name)
    for route, name in [('', 'dashboard'), ('trajets/', 'trajets'), ('offres/', 'offres'), ('vehicules/', 'vehicules'), ('transports/', 'transports')]
]
