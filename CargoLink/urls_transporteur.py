from django.urls import path
from django.views.generic import TemplateView

app_name = 'transporteur'

urlpatterns = [
    path(route, TemplateView.as_view(template_name=f'transporteur/{name}.html', extra_context={'active_tab': name}), name=name)
    for route, name in [('', 'dashboard'), ('trajets/', 'trajets'), ('demandes/', 'demandes'), ('offres/', 'offres'), ('vehicules/', 'vehicules'), ('transports/', 'transports'), ('avis/', 'avis')]
]
