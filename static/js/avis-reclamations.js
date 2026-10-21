// Module Avis & réclamations : contrôle de saisie lisible côté navigateur.
// Le serveur reste l'autorité : ces vérifications ne servent qu'à guider l'utilisateur plus tôt.
document.addEventListener('DOMContentLoaded', () => {
  const RATING_TEXT = { 1: 'Très insatisfaisant', 2: 'Insatisfaisant', 3: 'Correct', 4: 'Bien', 5: 'Excellent' };

  const longueur = (field) => (field.tagName === 'TEXTAREA' || field.type === 'text' ? field.value.trim().length : field.value.length);

  function messageErreur(field) {
    const v = field.validity;
    if (field.type === 'radio') return 'Attribuez une note de 1 à 5 étoiles.';
    if (v.valueMissing || (field.required && !field.value.trim())) return 'Ce champ est obligatoire.';
    if (field.minLength > 0 && longueur(field) < field.minLength) {
      return `Saisissez au moins ${field.minLength} caractères (actuellement ${longueur(field)}).`;
    }
    if (field.maxLength > 0 && field.value.length > field.maxLength) return `Saisissez au plus ${field.maxLength} caractères.`;
    if (v.badInput) return 'Saisissez un nombre valide.';
    if (v.rangeUnderflow) return `La valeur ne peut pas être inférieure à ${field.min}.`;
    if (v.rangeOverflow) return `La valeur ne peut pas dépasser ${field.max}.`;
    if (v.stepMismatch) return 'Utilisez au plus 2 chiffres après la virgule.';
    return field.validationMessage || 'Valeur invalide.';
  }

  function estInvalide(field) {
    if (field.disabled || field.type === 'hidden') return false;
    if (field.required && !field.value.trim() && field.type !== 'radio') return true;
    if (field.minLength > 0 && field.value.trim() && longueur(field) < field.minLength) return true;
    return !field.checkValidity();
  }

  function conteneur(field) {
    return field.closest('.ar-field, .ar-rating') || field.parentElement;
  }

  function effacerErreur(field) {
    const box = conteneur(field);
    field.classList.remove('is-invalid');
    field.removeAttribute('aria-invalid');
    box.classList.remove('is-invalid');
    box.querySelectorAll('[data-js-error]').forEach((node) => node.remove());
  }

  function afficherErreur(field, texte) {
    effacerErreur(field);
    const box = conteneur(field);
    const erreur = document.createElement('p');
    erreur.className = 'field-error';
    erreur.dataset.jsError = 'true';
    erreur.setAttribute('role', 'alert');
    erreur.textContent = texte;
    if (field.type === 'radio') {
      box.classList.add('is-invalid');
    } else {
      field.classList.add('is-invalid');
      field.setAttribute('aria-invalid', 'true');
    }
    box.appendChild(erreur);
  }

  // Compteurs de caractères
  document.querySelectorAll('textarea[data-counter]').forEach((area) => {
    const max = Number(area.dataset.counter);
    const min = area.minLength > 0 ? area.minLength : 0;
    const compteur = document.createElement('p');
    compteur.className = 'ar-counter';
    compteur.setAttribute('aria-live', 'polite');
    area.insertAdjacentElement('afterend', compteur);
    const maj = () => {
      const n = area.value.length;
      const manque = min && area.value.trim().length < min ? ` · minimum ${min}` : '';
      compteur.textContent = `${n} / ${max} caractères${manque}`;
      compteur.classList.toggle('warn', n > max * 0.9 && n <= max);
      compteur.classList.toggle('bad', n > max);
    };
    area.addEventListener('input', maj);
    maj();
  });

  // Texte sous les étoiles
  document.querySelectorAll('.ar-rating').forEach((block) => {
    const texte = block.querySelector('[data-rating-text]');
    const maj = () => {
      const choisi = block.querySelector('input:checked');
      texte.textContent = choisi ? `${choisi.value}/5 · ${RATING_TEXT[choisi.value]}` : 'Cliquez sur une étoile pour noter.';
    };
    block.addEventListener('change', maj);
    maj();
  });

  // Validation à l'envoi et nettoyage des erreurs pendant la saisie
  document.querySelectorAll('form[data-ar-form]').forEach((form) => {
    form.addEventListener('input', (event) => event.target.matches('input, select, textarea') && effacerErreur(event.target));
    form.addEventListener('change', (event) => event.target.matches('input, select, textarea') && effacerErreur(event.target));

    form.addEventListener('submit', (event) => {
      const vus = new Set();
      let premier = null;
      form.querySelectorAll('input, select, textarea').forEach((field) => {
        if (field.type === 'radio') {
          if (vus.has(field.name)) return;
          vus.add(field.name);
          const groupe = form.querySelectorAll(`input[type="radio"][name="${field.name}"]`);
          const requis = [...groupe].some((radio) => radio.required);
          if (requis && ![...groupe].some((radio) => radio.checked)) {
            afficherErreur(field, messageErreur(field));
            premier = premier || field;
          }
          return;
        }
        if (estInvalide(field)) {
          afficherErreur(field, messageErreur(field));
          premier = premier || field;
        }
      });
      if (premier) {
        event.preventDefault();
        premier.scrollIntoView({ block: 'center', behavior: 'smooth' });
        premier.focus({ preventScroll: true });
        return;
      }
      const bouton = form.querySelector('button[type="submit"]');
      if (bouton) {
        bouton.disabled = true;
        bouton.textContent = 'Envoi en cours…';
      }
    });
  });
});
