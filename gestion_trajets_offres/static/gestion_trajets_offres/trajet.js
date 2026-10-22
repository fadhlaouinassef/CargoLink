(() => {
  const content = document.querySelector('#module-dialog-content');
  if (!content) return;

  function updateCapacites() {
    const select = content.querySelector('[data-trajet-vehicule]');
    if (!select) return;
    const option = select.selectedOptions[0];
    select.form.elements.namedItem('capacite_kg').value = option?.dataset.capacite || '';
    select.form.elements.namedItem('volume_m3').value = option?.dataset.volume || '';
  }

  content.addEventListener('change', event => {
    if (event.target.matches('[data-trajet-vehicule]')) updateCapacites();
  });
  new MutationObserver(updateCapacites).observe(content, {childList: true});
  updateCapacites();
})();
