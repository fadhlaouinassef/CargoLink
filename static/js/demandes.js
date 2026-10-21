document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-digits-only]').forEach((input) => {
    input.addEventListener('input', () => {
      input.value = input.value.replace(/\D/g, '');
    });
  });

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
