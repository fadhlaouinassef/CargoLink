(() => {
  const dialog = document.querySelector('#module-dialog');
  const content = document.querySelector('#module-dialog-content');
  const feedback = document.querySelector('#module-feedback');
  if (!dialog) return;

  function busy(button, loading) {
    if (!button) return;
    button.disabled = loading;
    if (loading) {
      button.dataset.originalLabel = button.textContent;
      button.textContent = 'Chargement…';
      const spinner = document.createElement('span');
      spinner.className = 'module-spinner';
      spinner.setAttribute('aria-hidden', 'true');
      button.prepend(spinner);
      button.setAttribute('aria-busy', 'true');
    } else {
      button.textContent = button.dataset.originalLabel;
      button.removeAttribute('aria-busy');
    }
  }

  function showError(message) {
    const target = dialog.open ? content.querySelector('[data-popup-error]') : feedback;
    if (target) {
      target.textContent = message;
      target.hidden = false;
    }
  }

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function formattedDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? value
      : new Intl.DateTimeFormat('fr-FR', {dateStyle: 'medium', timeStyle: 'short'}).format(date);
  }

  function formattedCalendarDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    if (!match) return value || '';
    return new Intl.DateTimeFormat('fr-FR').format(new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  }

  function stateMessage(container, message, isError = false, retry = false) {
    container.replaceChildren();
    const text = node('p', isError ? 'module-error' : 'ranking-empty', message);
    text.setAttribute('role', isError ? 'alert' : 'status');
    container.append(text);
    if (retry) {
      const button = node('button', 'btn-secondary', 'Réessayer');
      button.type = 'button';
      button.dataset.retryRanking = '';
      container.append(button);
    }
  }

  function appendDetail(list, label, value) {
    const item = node('li');
    item.append(node('span', '', label), node('strong', '', value || 'Non renseigné'));
    list.append(item);
  }

  function renderOffer(offer, index, csrfToken) {
    const card = node('article', `received-offer ranking-offer${index === 0 ? ' ranking-offer-best' : ''}`);
    const heading = node('div', 'received-offer-heading');
    const identity = node('div', 'ranking-offer-identity');
    identity.append(node('strong', '', offer.transporteur.nom || 'Transporteur'));
    if (index === 0) identity.append(node('span', 'matching-best-badge', 'Meilleur score de matching'));
    heading.append(identity, node('strong', 'ranking-price', `${Number(offer.prix).toLocaleString('fr-FR')} TND`));
    card.append(heading);

    const ranking = node('p', 'ranking-score', `Rang ${offer.rang} · Score de classement : ${offer.score}`);
    card.append(ranking);

    const details = node('ul', 'ranking-details');
    const vehicle = offer.details_vehicule
      ? `${offer.details_vehicule.description} (${offer.details_vehicule.type})`
      : offer.vehicule_reference || 'Véhicule non référencé';
    appendDetail(details, 'Véhicule', vehicle);
    appendDetail(details, 'Trajet', `${offer.trajet.depart} → ${offer.trajet.arrivee}`);
    appendDetail(details, 'Capacité disponible', `${offer.capacites.poids_kg} kg · ${offer.capacites.volume_m3} m³`);
    appendDetail(details, 'Date de départ', formattedDate(offer.trajet.date_depart));
    appendDetail(details, 'Période souhaitée',
      `${formattedCalendarDate(offer.demande_date_depart)} – ${formattedCalendarDate(offer.demande_date_limite)}`);
    card.append(details);

    const status = node('p', 'module-small', `Transporteur : ${offer.transporteur.note}/5 (${offer.transporteur.nombre_avis} avis)`);
    card.append(status);

    if (offer.url_accepter) {
      const form = document.createElement('form');
      form.method = 'post';
      form.action = offer.url_accepter;
      form.dataset.moduleForm = '';
      const csrf = document.createElement('input');
      csrf.type = 'hidden';
      csrf.name = 'csrfmiddlewaretoken';
      csrf.value = csrfToken;
      form.append(csrf);
      const error = node('p', 'module-error');
      error.dataset.popupError = '';
      error.hidden = true;
      form.append(error);
      const actions = node('div', 'module-dialog-actions');
      const accept = node('button', 'btn-primary', 'Choisir et accepter cette offre');
      accept.type = 'submit';
      actions.append(accept);
      form.append(actions);
      card.append(form);
    } else if (offer.statut_offre === 'acceptee') {
      card.append(node('span', 'badge badge-active', 'Offre acceptée'));
    }

    return card;
  }

  function renderExcluded(offers, title) {
    if (!offers.length) return null;
    const section = node('section', 'ranking-excluded');
    section.append(node('h3', '', title));
    offers.forEach(offer => {
      const item = node('article', 'ranking-excluded-item');
      item.append(node('strong', '', `${offer.transporteur.nom} · ${Number(offer.prix).toLocaleString('fr-FR')} TND`));
      const reasons = node('ul');
      offer.motifs.forEach(reason => reasons.append(node('li', '', reason)));
      item.append(reasons);
      section.append(item);
    });
    return section;
  }

  async function loadRanking(root) {
    const state = root.querySelector('[data-ranking-state]');
    if (!state) return;
    stateMessage(state, 'Chargement du classement des offres…');
    const spinner = node('span', 'module-spinner');
    spinner.setAttribute('aria-hidden', 'true');
    state.prepend(spinner);
    try {
      const response = await fetch(root.dataset.rankingUrl, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('Impossible de charger le classement. Rechargez la page puis réessayez.');
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Le classement est momentanément indisponible.');
      const warning = root.querySelector('.ranking-score-warning');
      if (warning && data.avertissement) warning.textContent = data.avertissement;
      state.replaceChildren();
      if (data.statut === 'ok') {
        data.offres.forEach((offer, index) => {
          offer.demande_date_depart = data.demande.date_depart;
          offer.demande_date_limite = data.demande.date_limite;
          state.append(renderOffer(offer, index, root.querySelector('[name="csrfmiddlewaretoken"]')?.value || ''));
        });
      } else {
        stateMessage(state, data.message);
      }
      const excluded = renderExcluded(data.exclues, 'Offres exclues et motifs');
      const notEvaluable = renderExcluded(data.non_evaluables, 'Offres non évaluables');
      if (excluded) state.append(excluded);
      if (notEvaluable) state.append(notEvaluable);
    } catch (error) {
      stateMessage(state, error.message || 'Le classement est momentanément indisponible.', true, true);
    }
  }

  async function readResponse(response) {
    if (response.redirected) throw new Error('Votre session a expiré. Reconnectez-vous.');
    if (!response.headers.get('content-type')?.includes('application/json')) {
      throw new Error('Impossible de terminer cette action. Rechargez la page puis réessayez.');
    }
    const data = await response.json();
    if (data.error) throw new Error(data.error);
    if (!response.ok && !data.html) throw new Error('Une erreur est survenue. Réessayez.');
    return data;
  }

  document.addEventListener('click', async event => {
    if (event.target.closest('[data-close-dialog]')) {
      dialog.close();
      return;
    }
    const button = event.target.closest('[data-popup-url]');
    if (!button || button.disabled) return;
    feedback.hidden = true;
    busy(button, true);
    try {
      const data = await readResponse(await fetch(button.dataset.popupUrl));
      content.innerHTML = data.html;
      dialog.showModal();
      const ranking = content.querySelector('[data-ranking-url]');
      if (ranking) loadRanking(ranking);
    } catch (error) {
      showError(error.message);
    } finally {
      busy(button, false);
    }
  });

  dialog.addEventListener('click', event => {
    const retry = event.target.closest('[data-retry-ranking]');
    if (retry) {
      const ranking = content.querySelector('[data-ranking-url]');
      if (ranking) loadRanking(ranking);
      return;
    }
    if (event.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    }
  });

  dialog.addEventListener('submit', async event => {
    const form = event.target.closest('[data-module-form]');
    if (!form) return;
    event.preventDefault();
    if (form.dataset.submitting) return;
    const button = form.querySelector('[type="submit"]');
    form.dataset.submitting = 'true';
    const formError = form.querySelector('[data-popup-error]');
    if (formError) formError.hidden = true;
    busy(button, true);
    try {
      const data = await readResponse(await fetch(form.action, {method: 'POST', body: new FormData(form)}));
      if (data.success) {
        window.location.reload();
        return;
      }
      content.innerHTML = data.html;
      const ranking = content.querySelector('[data-ranking-url]');
      if (ranking) loadRanking(ranking);
      content.querySelector('[aria-invalid="true"], input:not([type="hidden"]), select, [data-close-dialog]')?.focus();
    } catch (error) {
      showError(error.message);
    } finally {
      delete form.dataset.submitting;
      busy(button, false);
    }
  });
})();
