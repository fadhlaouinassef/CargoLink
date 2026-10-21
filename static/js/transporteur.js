const feedback = document.querySelector('#demo-feedback');
const confirmationModal = document.querySelector('#confirm-modal');
let pendingDeleteForm = null;
function closeConfirmation() {
  if (!confirmationModal) return;
  confirmationModal.hidden = true;
  document.body.classList.remove('confirmation-open');
  pendingDeleteForm = null;
}
document.querySelectorAll('[data-confirm-delete]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!confirmationModal) return;
    event.preventDefault();
    pendingDeleteForm = form;
    document.querySelector('#confirm-message').textContent = form.dataset.confirmDelete;
    confirmationModal.hidden = false;
    document.body.classList.add('confirmation-open');
    document.querySelector('[data-confirm-submit]').focus();
  });
});
if (confirmationModal) {
  confirmationModal.querySelectorAll('[data-confirm-cancel], .confirm-modal-close').forEach(button => button.addEventListener('click', closeConfirmation));
  confirmationModal.querySelector('[data-confirm-submit]').addEventListener('click', () => {
    if (pendingDeleteForm) {
      const form = pendingDeleteForm;
      pendingDeleteForm = null;
      form.submit();
    }
  });
  confirmationModal.addEventListener('click', event => { if (event.target === confirmationModal) closeConfirmation(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeConfirmation(); });
}
document.querySelectorAll('[data-demo-form]').forEach(form => {
  form.addEventListener('submit', event => {
    event.preventDefault();
    const start = form.elements.namedItem('start');
    const end = form.elements.namedItem('end');
    if (start && end && end.value <= start.value) {
      end.setCustomValidity('La fin doit être postérieure au début.');
      end.reportValidity();
      return;
    }
    if (form.hasAttribute('data-tracking')) {
      const item = document.createElement('div');
      item.className = 'event-log-item';
      const title = document.createElement('div');
      title.className = 'event-log-title';
      title.textContent = form.elements.stage.value;
      const desc = document.createElement('p');
      desc.className = 'event-log-desc';
      desc.textContent = form.elements.location.value;
      item.append(title, desc);
      document.querySelector('#carrier-events').prepend(item);
    }
    feedback.textContent = 'Simulation effectuée. Aucune donnée n’a été envoyée ou enregistrée sur le serveur.';
    feedback.hidden = false;
    feedback.scrollIntoView({ block: 'center' });
  });
  form.addEventListener('input', () => {
    const end = form.elements.namedItem('end');
    if (end) end.setCustomValidity('');
  });
});
document.querySelectorAll('[data-offer]').forEach(button => {
  button.addEventListener('click', () => {
    const reference = document.querySelector('#offer-reference');
    reference.value = button.dataset.offer;
    reference.focus();
  });
});
const search = document.querySelector('#demand-search');
if (search) {
  const filter = () => {
    let visible = 0;
    document.querySelectorAll('#demand-results tbody tr').forEach(row => {
      row.hidden = !row.textContent.toLocaleLowerCase('fr').includes(search.value.trim().toLocaleLowerCase('fr'));
      if (!row.hidden) visible++;
    });
    document.querySelector('#no-demands').hidden = visible > 0;
  };
  search.addEventListener('input', filter);
  document.querySelector('#carrier-search').addEventListener('submit', event => { event.preventDefault(); filter(); });
}
