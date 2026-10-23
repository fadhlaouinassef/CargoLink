(() => {
  document.addEventListener('submit', async event => {
    const form = event.target.closest('[data-rapport-form]');
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector('button');
    if (button.disabled) return;
    const feedback = document.querySelector('#module-feedback');
    if (feedback) feedback.hidden = true;
    button.disabled = true;
    button.textContent = 'Génération en cours…';
    button.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(form.action, {method: 'POST', body: new FormData(form)});
      if (response.redirected) throw new Error('Votre session a expiré. Reconnectez-vous.');
      if (!response.ok) {
        const data = response.headers.get('content-type')?.includes('application/json')
          ? await response.json() : {};
        throw new Error(data.error || 'Impossible de générer le rapport. Rechargez la page puis réessayez.');
      }
      if (!response.headers.get('content-type')?.includes('application/pdf')) {
        throw new Error('Le serveur n’a pas renvoyé de rapport PDF.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = form.dataset.filename;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (error) {
      if (feedback) {
        feedback.textContent = error.message;
        feedback.hidden = false;
      }
    } finally {
      button.disabled = false;
      button.textContent = 'Générer Rapport';
      button.removeAttribute('aria-busy');
    }
  });
})();
