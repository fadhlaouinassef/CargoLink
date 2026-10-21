from django.urls import path
from django.views.generic import TemplateView

from gestion_trajets.decorators import transporteur_required
from gestion_trajets.urls import urlpatterns as module_urls

app_name = 'transporteur'

urlpatterns = module_urls + [
    path(route, transporteur_required(TemplateView.as_view(
        template_name=f'transporteur/{name}.html', extra_context={'active_tab': name}
    )), name=name)
    for route, name in [('', 'dashboard'), ('vehicules/', 'vehicules'), ('avis/', 'avis')]
]
