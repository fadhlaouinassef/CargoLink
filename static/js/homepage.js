const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
function closeMenu() { menuButton.setAttribute('aria-expanded', 'false'); menuButton.querySelector('.sr-only').textContent = 'Ouvrir le menu'; navigation.classList.remove('is-open'); }
menuButton.addEventListener('click', () => {
  const open = menuButton.getAttribute('aria-expanded') !== 'true';
  menuButton.setAttribute('aria-expanded', String(open));
  menuButton.querySelector('.sr-only').textContent = open ? 'Fermer le menu' : 'Ouvrir le menu';
  navigation.classList.toggle('is-open', open);
});
navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
const dialog = document.querySelector('#information-dialog');
function showInformation(title, description) {
  document.querySelector('#dialog-title').textContent = title;
  document.querySelector('#dialog-description').textContent = description;
  closeMenu();
  dialog.showModal();
}
document.querySelectorAll('.dialog-close, .dialog-dismiss').forEach(button => button.addEventListener('click', () => dialog.close()));
dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });
const actions = {
  entreprise: ['Votre prochaine expédition commence ici', 'L’espace entreprise est en préparation. Vous pourrez y préciser votre trajet, votre date et vos marchandises, puis comparer les offres de transport. Aucune demande n’est publiée depuis cette page de présentation.'],
  transporteur: ['Donnez une destination à votre espace disponible', 'L’espace transporteur est en préparation. Vous pourrez y proposer vos trajets et renseigner les capacités de votre véhicule. Aucun trajet n’est publié depuis cette page de présentation.'],
  inscription: ['Rejoindre CargoLink', 'Les inscriptions ne sont pas encore ouvertes. CargoLink prépare un espace pour les entreprises et un espace pour les transporteurs indépendants.'],
  connexion: ['Se connecter à CargoLink', 'La connexion sera disponible à l’ouverture des espaces entreprise et transporteur.']
};
document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => showInformation(...actions[button.dataset.action])));
const information = {
  about: ['À propos de CargoLink', 'CargoLink est un projet de plateforme tunisienne qui rapproche les PME ayant des marchandises à expédier et les transporteurs indépendants disposant de capacités disponibles. Son objectif : réduire les trajets à vide et mieux utiliser les véhicules.'],
  contact: ['Contact', 'Les coordonnées de contact seront communiquées lors du lancement de CargoLink. Aucun formulaire de contact n’est disponible pour le moment.'],
  terms: ['Conditions d’utilisation', 'Cette page présente le projet CargoLink et des trajets fictifs. Elle ne permet ni réservation ni transaction. Les conditions d’utilisation du service seront publiées avant son ouverture.'],
  privacy: ['Confidentialité', 'Les champs de recherche servent uniquement à filtrer les exemples dans votre navigateur. Leurs valeurs ne sont ni transmises par ce formulaire ni enregistrées. Cette page charge des polices depuis Google Fonts ; ce fournisseur reçoit les informations techniques nécessaires à leur chargement. La politique de confidentialité du service sera précisée avant son ouverture.']
};
document.querySelectorAll('[data-info]').forEach(button => button.addEventListener('click', () => showInformation(...information[button.dataset.info])));
document.querySelectorAll('[data-route]').forEach(button => button.addEventListener('click', () => showInformation(button.dataset.route, `${button.dataset.details}\n\nCe trajet et ses capacités sont fictifs, à titre d’illustration. Aucune date ni disponibilité réelle n’est associée à cet exemple. Il ne peut pas être réservé.`)));
const form = document.querySelector('#route-search');
const status = document.querySelector('#search-status');
const reset = document.querySelector('#reset-search');
const cards = [...document.querySelectorAll('.route-card')];
form.addEventListener('submit', event => {
  event.preventDefault();
  const departure = form.elements.departure.value;
  const arrival = form.elements.arrival.value;
  let count = 0;
  cards.forEach(card => {
    const match = (!departure || card.dataset.departure === departure) && (!arrival || card.dataset.arrival === arrival);
    card.hidden = !match;
    if (match) count++;
  });
  status.hidden = false;
  status.textContent = count ? `${count} exemple${count > 1 ? 's' : ''} de trajet correspond${count > 1 ? 'ent' : ''} aux villes sélectionnées. Ces données sont fictives et ne représentent pas des disponibilités à la date souhaitée.` : 'Aucun exemple ne correspond à ces villes. Ces données fictives ne représentent pas les trajets disponibles sur la future plateforme.';
  reset.hidden = false;
  document.querySelector('#trajets').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
});
reset.addEventListener('click', () => { form.reset(); cards.forEach(card => { card.hidden = false; }); status.hidden = true; reset.hidden = true; document.querySelector('#departure').focus({ preventScroll: true }); });
