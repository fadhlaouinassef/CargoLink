document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-digits-only]').forEach((input) => {
    input.addEventListener('input', () => {
      input.value = input.value.replace(/\D/g, '');
    });
  });

  const demandForm = document.querySelector('form[method="post"]');
  if (demandForm) {
    demandForm.addEventListener('click', async (event) => {
      const button = event.target.closest('.btn-ai-description');
      if (!button) return;

      const row = button.closest('.goods-row');
      const description = row.querySelector('input[name$="-description"]');
      const status = row.querySelector('.ai-description-status');
      const csrfToken = demandForm.querySelector('[name="csrfmiddlewaretoken"]')?.value;
      const fieldValue = (name) => demandForm.querySelector(`[name="${name}"]`)?.value || '';
      const fieldChecked = (name) => Boolean(demandForm.querySelector(`[name="${name}"]`)?.checked);
      const typeField = row.querySelector('select[name$="-type"]');
      const requestData = {
        depart_ville: fieldValue('depart_ville'),
        arrivee_ville: fieldValue('arrivee_ville'),
        date_depart: fieldValue('date_depart'),
        date_limite: fieldValue('date_limite'),
        hayon: fieldChecked('hayon'),
        transpalette: fieldChecked('transpalette'),
        bache: fieldChecked('bache'),
        marchandise: {
          description: description.value,
          type: typeField?.selectedOptions[0]?.textContent.trim() || '',
          poids: row.querySelector('input[name$="-poids"]')?.value || '',
          volume: row.querySelector('input[name$="-volume"]')?.value || '',
          fragile: Boolean(row.querySelector('input[name$="-fragile"]')?.checked),
        },
      };

      button.disabled = true;
      button.textContent = 'Génération…';
      status.textContent = '';
      status.classList.remove('error');
      try {
        const response = await fetch(button.dataset.aiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify(requestData),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Impossible de générer la description.');
        description.value = result.description;
        description.dispatchEvent(new Event('input', { bubbles: true }));
        status.textContent = 'Description proposée. Vérifiez-la avant d’enregistrer.';
      } catch (error) {
        status.textContent = error.message || 'Le service IA est indisponible.';
        status.classList.add('error');
      } finally {
        button.disabled = false;
        button.textContent = 'Améliorer avec IA';
      }
    });
  }

  const addButton = document.querySelector('#btn-add-goods');
  const rows = document.querySelector('#goods-table-body');
  const template = document.querySelector('#empty-good-form');
  const totalForms = document.querySelector('#id_marchandises-TOTAL_FORMS');

  if (!addButton || !rows || !template || !totalForms) return;

  addButton.addEventListener('click', () => {
    const index = Number(totalForms.value);
    const rowHtml = template.innerHTML.replaceAll('__prefix__', index);
    rows.insertAdjacentHTML('beforeend', rowHtml);
    totalForms.value = index + 1;
    rows.lastElementChild.querySelector('input:not([type="hidden"])')?.focus();
  });

  rows.addEventListener('click', (event) => {
    const button = event.target.closest('.btn-remove-row');
    if (!button) return;
    const row = button.closest('.goods-row');
    const deleteInput = row.querySelector('input[name$="-DELETE"]');
    if (deleteInput) {
      deleteInput.checked = true;
      row.hidden = true;
    } else {
      row.remove();
    }
  });
});
