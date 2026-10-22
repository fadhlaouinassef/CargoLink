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
    } catch (error) {
      showError(error.message);
    } finally {
      busy(button, false);
    }
  });

  dialog.addEventListener('click', event => {
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
    form.querySelector('[data-popup-error]').hidden = true;
    busy(button, true);
    try {
      const data = await readResponse(await fetch(form.action, {method: 'POST', body: new FormData(form)}));
      if (data.success) {
        window.location.reload();
        return;
      }
      content.innerHTML = data.html;
      content.querySelector('[aria-invalid="true"], input:not([type="hidden"]), select, [data-close-dialog]')?.focus();
    } catch (error) {
      showError(error.message);
    } finally {
      delete form.dataset.submitting;
      busy(button, false);
    }
  });
})();
