/**
 * Assistant IA de saisie en langage naturel pour le formulaire de disponibilité
 * Module vehicules - CargoLink
 * WCAG AA accessible, JS vanilla sans dépendance.
 */
document.addEventListener('DOMContentLoaded', function () {
  const container = document.getElementById('assistant-ia-container');
  if (!container) return;

  const phraseInput = document.getElementById('assistant-ia-phrase');
  const btnSubmit = document.getElementById('assistant-ia-submit');
  const charCounter = document.getElementById('assistant-ia-counter');
  const liveRegion = document.getElementById('assistant-ia-live');
  const alertRegion = document.getElementById('assistant-ia-alert');
  const summaryRegion = document.getElementById('assistant-ia-summary');
  const btnSpinner = document.getElementById('assistant-ia-spinner');
  const btnText = document.getElementById('assistant-ia-btn-text');

  const endpointUrl = container.getAttribute('data-endpoint');
  const form = document.getElementById('form-disponibilite');

  if (!phraseInput || !btnSubmit || !endpointUrl || !form) return;

  // Récupération des champs du formulaire de disponibilité
  const fieldVehicule = form.querySelector('[name="vehicule"]');
  const fieldDateDebut = form.querySelector('[name="date_debut"]');
  const fieldDateFin = form.querySelector('[name="date_fin"]');
  const fieldZoneDepart = form.querySelector('[name="zone_depart"]');
  const fieldZoneArrivee = form.querySelector('[name="zone_arrivee"]');
  const fieldCommentaire = form.querySelector('[name="commentaire"]');

  const trackedFields = [
    { el: fieldZoneDepart, name: 'zone_depart', label: 'Zone de départ' },
    { el: fieldZoneArrivee, name: 'zone_arrivee', label: 'Zone d’arrivée' },
    { el: fieldDateDebut, name: 'date_debut', label: 'Date de début' },
    { el: fieldDateFin, name: 'date_fin', label: 'Date de fin' },
    { el: fieldVehicule, name: 'vehicule', label: 'Véhicule' },
    { el: fieldCommentaire, name: 'commentaire', label: 'Commentaire' },
  ];

  // Helper pour lire le cookie CSRF
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + '=') {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // Mise à jour du compteur de caractères et validation active
  function updateState() {
    const len = phraseInput.value.trim().length;
    charCounter.textContent = `${phraseInput.value.length} / 300 caractères`;
    btnSubmit.disabled = len < 3 || len > 300;
  }

  phraseInput.addEventListener('input', updateState);
  updateState();

  // Nettoyage du badge "suggéré par l'IA" dès modification manuelle
  trackedFields.forEach(item => {
    if (!item.el) return;
    const cleanBadge = function () {
      item.el.classList.remove('ia-suggested-field');
      const badge = item.el.parentElement ? item.el.parentElement.querySelector('.ia-suggested-badge') : null;
      if (badge) badge.remove();
    };
    item.el.addEventListener('input', cleanBadge);
    item.el.addEventListener('change', cleanBadge);
  });

  function markFieldAsSuggested(element, labelText) {
    if (!element) return;
    element.classList.add('ia-suggested-field');
    const parent = element.parentElement;
    if (parent && !parent.querySelector('.ia-suggested-badge')) {
      const badge = document.createElement('span');
      badge.className = 'ia-suggested-badge';
      badge.setAttribute('aria-label', `Valeur suggérée par l'IA pour ${labelText}`);
      badge.innerHTML = `<span aria-hidden="true">✨</span> Suggéré par l'IA`;
      parent.insertBefore(badge, element);
    }
  }

  function resetFeedback() {
    if (alertRegion) {
      alertRegion.textContent = '';
      alertRegion.hidden = true;
    }
    if (summaryRegion) {
      summaryRegion.innerHTML = '';
      summaryRegion.hidden = true;
    }
  }

  function showAlert(msg) {
    if (!alertRegion) return;
    alertRegion.textContent = msg;
    alertRegion.hidden = false;
    alertRegion.focus();
  }

  // Clic sur "Remplir avec l'IA"
  btnSubmit.addEventListener('click', async function (e) {
    e.preventDefault();
    const phrase = phraseInput.value.trim();
    if (phrase.length < 3 || phrase.length > 300) return;

    resetFeedback();

    // État de chargement
    btnSubmit.disabled = true;
    if (btnSpinner) btnSpinner.hidden = false;
    if (btnText) btnText.textContent = 'Analyse en cours...';
    if (liveRegion) liveRegion.textContent = 'Analyse en cours, veuillez patienter...';

    // Timeout client de 20s
    const controller = new AbortController();
    const clientTimeout = setTimeout(() => controller.abort(), 20000);

    const csrfToken = getCookie('csrftoken') || (form.querySelector('[name=csrfmiddlewaretoken]') ? form.querySelector('[name=csrfmiddlewaretoken]').value : '');

    try {
      const response = await fetch(endpointUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ phrase: phrase }),
        signal: controller.signal,
      });

      clearTimeout(clientTimeout);
      const data = await response.json();

      if (!response.ok || !data.success) {
        const errorMsg = data.error || `Erreur serveur (${response.status}).`;
        showAlert(errorMsg);
        if (liveRegion) liveRegion.textContent = `Erreur : ${errorMsg}`;
        return;
      }

      // Remplissage des champs
      const champs = data.champs || {};
      let filledCount = 0;

      if (champs.zone_depart && fieldZoneDepart) {
        fieldZoneDepart.value = champs.zone_depart;
        markFieldAsSuggested(fieldZoneDepart, 'Zone de départ');
        filledCount++;
      }

      if (champs.zone_arrivee && fieldZoneArrivee) {
        fieldZoneArrivee.value = champs.zone_arrivee;
        markFieldAsSuggested(fieldZoneArrivee, 'Zone d’arrivée');
        filledCount++;
      }

      if (champs.date_debut && fieldDateDebut) {
        fieldDateDebut.value = champs.date_debut;
        markFieldAsSuggested(fieldDateDebut, 'Date de début');
        filledCount++;
      }

      if (champs.date_fin && fieldDateFin) {
        fieldDateFin.value = champs.date_fin;
        markFieldAsSuggested(fieldDateFin, 'Date de fin');
        filledCount++;
      }

      if (champs.commentaire && fieldCommentaire) {
        fieldCommentaire.value = champs.commentaire;
        markFieldAsSuggested(fieldCommentaire, 'Commentaire');
        filledCount++;
      }

      // Résolution du véhicule
      const vehiculesData = data.vehicules || {};
      let vehiculeMessage = '';
      if (vehiculesData.vehicule_selectionne_id && fieldVehicule) {
        fieldVehicule.value = String(vehiculesData.vehicule_selectionne_id);
        markFieldAsSuggested(fieldVehicule, 'Véhicule');
        filledCount++;
      } else if (vehiculesData.candidats && vehiculesData.candidats.length > 1) {
        vehiculeMessage = `Plusieurs véhicules de votre flotte correspondent (${vehiculesData.candidats.length}). Veuillez en sélectionner un ci-dessous.`;
        if (fieldVehicule) fieldVehicule.focus();
      } else if (vehiculesData.message) {
        vehiculeMessage = vehiculesData.message;
      }

      // Construction du résumé récapitulatif accessible
      if (summaryRegion) {
        let html = '<div class="ia-summary-card">';
        html += '<div class="ia-summary-title"><strong>✨ Informations pré-remplies par l’assistant IA</strong></div>';
        html += '<p class="ia-summary-help">Vérifiez les valeurs ci-dessous, ajustez-les si besoin, puis enregistrez la disponibilité.</p>';

        if (vehiculeMessage) {
          html += `<div class="ia-summary-alert-info" role="status">👉 <strong>Véhicule :</strong> ${vehiculeMessage}</div>`;
        }

        if (data.champs_manquants && data.champs_manquants.length > 0) {
          const labelsMap = {
            zone_depart: 'Zone de départ',
            zone_arrivee: 'Zone d’arrivée',
            date_debut: 'Date de début',
            date_fin: 'Date de fin',
            vehicule: 'Véhicule',
          };
          const manquantsLisibles = data.champs_manquants.map(k => labelsMap[k] || k).join(', ');
          html += `<div class="ia-summary-warning">⚠️ <strong>Champs à compléter manuellement :</strong> ${manquantsLisibles}.</div>`;
        }

        if (data.avertissements && data.avertissements.length > 0) {
          html += '<ul class="ia-summary-warnings">';
          data.avertissements.forEach(w => {
            html += `<li>ℹ️ ${w}</li>`;
          });
          html += '</ul>';
        }

        html += '</div>';
        summaryRegion.innerHTML = html;
        summaryRegion.hidden = false;
      }

      if (liveRegion) {
        liveRegion.textContent = `Formulaire pré-rempli avec succès. ${filledCount} champs ont été renseignés. Vérifiez puis enregistrez.`;
      }

    } catch (err) {
      clearTimeout(clientTimeout);
      let errorMsg = "Impossible de joindre l'assistant IA. Le formulaire manuel reste accessible.";
      if (err.name === 'AbortError') {
        errorMsg = "L'assistant IA a mis trop de temps à répondre (timeout). Vous pouvez réessayer ou remplir manuellement.";
      }
      showAlert(errorMsg);
      if (liveRegion) liveRegion.textContent = `Erreur : ${errorMsg}`;
    } finally {
      btnSubmit.disabled = false;
      if (btnSpinner) btnSpinner.hidden = true;
      if (btnText) btnText.textContent = 'Remplir avec l’IA';
      updateState();
    }
  });
});
