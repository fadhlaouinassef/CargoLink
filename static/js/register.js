const registerForm = document.querySelector('#register-form');
if (registerForm) {
  const password = registerForm.querySelector('#id_password');
  const confirmation = registerForm.querySelector('#id_password_confirmation');
  const button = registerForm.querySelector('.submit-button');
  const status = document.querySelector('#register-status');
  const updateRequirements = () => {
    const rules = {
      length: [...password.value].length >= 8,
      numeric: password.value.length > 0 && !/^\p{Decimal_Number}+$/u.test(password.value),
      match: password.value.length > 0 && password.value === confirmation.value,
    };
    for (const [name, valid] of Object.entries(rules)) {
      const item = document.querySelector(`[data-rule="${name}"]`);
      item.classList.toggle('is-valid', valid);
      item.querySelector('span').textContent = valid ? '✓' : '✕';
    }
    confirmation.setCustomValidity(confirmation.value && confirmation.value !== password.value
      ? 'Les mots de passe ne correspondent pas.' : '');
  };
  password.addEventListener('input', updateRequirements);
  confirmation.addEventListener('input', updateRequirements);
  registerForm.addEventListener('submit', event => {
    if (button.disabled) { event.preventDefault(); return; }
    button.disabled = true;
    registerForm.setAttribute('aria-busy', 'true');
    button.querySelector('.submit-label').textContent = 'Création en cours…';
    button.querySelector('.submit-spinner').hidden = false;
    button.querySelector('.submit-arrow').hidden = true;
    status.hidden = false;
  });
  window.addEventListener('pageshow', () => {
    button.disabled = false;
    registerForm.removeAttribute('aria-busy');
    button.querySelector('.submit-label').textContent = 'Créer mon compte';
    button.querySelector('.submit-spinner').hidden = true;
    button.querySelector('.submit-arrow').hidden = false;
    status.hidden = true;
    updateRequirements();
  });
  updateRequirements();
}
