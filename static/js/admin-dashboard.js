const users = [
  {name:'Amine Khelifi', email:'amine.khelifi@cargolink.tn', initials:'AK', role:'admin', roleLabel:'Admin', date:'12 oct. 2024', status:'active', statusLabel:'Actif', activity:'Il y a 5 min', color:''},
  {name:'Société Ben Salah', email:'contact@bensalah.tn', initials:'SB', role:'PME', roleLabel:'PME', date:'10 oct. 2024', status:'active', statusLabel:'Actif', activity:'Il y a 24 min', color:'sand'},
  {name:'Mohamed Trabelsi', email:'m.trabelsi@email.tn', initials:'MT', role:'transporteur', roleLabel:'Transporteur', date:'08 oct. 2024', status:'active', statusLabel:'Actif', activity:'Hier, 16:42', color:'blue'},
  {name:'Nour El Houda', email:'nour.elhouda@email.tn', initials:'NE', role:'destinataire', roleLabel:'Destinataire', date:'06 oct. 2024', status:'pending', statusLabel:'En attente', activity:'Il y a 2 jours', color:'purple'},
  {name:'Atelier Tunis Nord', email:'bonjour@atn.tn', initials:'AT', role:'PME', roleLabel:'PME', date:'05 oct. 2024', status:'active', statusLabel:'Actif', activity:'Il y a 3 jours', color:'sand'},
  {name:'Yassine Gharbi', email:'y.gharbi@email.tn', initials:'YG', role:'transporteur', roleLabel:'Transporteur', date:'02 oct. 2024', status:'inactive', statusLabel:'Inactif', activity:'Il y a 8 jours', color:'blue'}
];

const table = document.querySelector('#users-table');
const emptyState = document.querySelector('#empty-state');
const searchInput = document.querySelector('#user-search');
const roleFilter = document.querySelector('#role-filter');
const statusFilter = document.querySelector('#status-filter');
const visibleCount = document.querySelector('#visible-count');
const totalCount = document.querySelector('#total-count');
const totalUsers = document.querySelector('#total-users');
const toast = document.querySelector('#toast');
const createModal = document.querySelector('#create-user-modal');
const deleteModal = document.querySelector('#delete-user-modal');
const createForm = document.querySelector('#create-user-form');
const deleteUserName = document.querySelector('#delete-user-name');
let userToDelete = null;

const roleLabels = {admin: 'Admin', PME: 'PME', transporteur: 'Transporteur', destinataire: 'Destinataire'};
const statusLabels = {active: 'Actif', pending: 'En attente', inactive: 'Inactif'};
function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[character]));
}

function renderUsers() {
  const query = searchInput.value.trim().toLowerCase();
  const filteredUsers = users.filter(user => {
    const matchesQuery = !query || `${user.name} ${user.email}`.toLowerCase().includes(query);
    const matchesRole = roleFilter.value === 'all' || user.role === roleFilter.value;
    const matchesStatus = statusFilter.value === 'all' || user.status === statusFilter.value;
    return matchesQuery && matchesRole && matchesStatus;
  });

  table.innerHTML = filteredUsers.map(user => `
    <tr>
      <td><input type="checkbox" aria-label="Sélectionner ${escapeHTML(user.name)}"></td>
      <td><div class="user-cell"><span class="user-avatar ${user.color}">${escapeHTML(user.initials)}</span><span><strong>${escapeHTML(user.name)}</strong><small>${escapeHTML(user.email)}</small></span></div></td>
      <td><span class="role-badge ${user.role}">${escapeHTML(user.roleLabel)}</span></td>
      <td>${escapeHTML(user.date)}</td>
      <td><span class="status-badge ${user.status}">${escapeHTML(user.statusLabel)}</span></td>
      <td>${escapeHTML(user.activity)}</td>
      <td><button class="row-action" type="button" aria-label="Supprimer ${escapeHTML(user.name)}" data-user="${escapeHTML(user.name)}">⌫</button></td>
    </tr>
  `).join('');
  visibleCount.textContent = filteredUsers.length;
  totalCount.textContent = users.length;
  totalUsers.textContent = users.length;
  emptyState.hidden = filteredUsers.length !== 0;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('visible');
  window.setTimeout(() => toast.classList.remove('visible'), 2600);
}

[searchInput, roleFilter, statusFilter].forEach(control => control.addEventListener('input', renderUsers));
document.querySelector('#select-all').addEventListener('change', event => {
  table.querySelectorAll('input[type="checkbox"]').forEach(checkbox => { checkbox.checked = event.target.checked; });
});
document.querySelector('#export-button').addEventListener('click', () => showToast('Export frontend simulé : la fonctionnalité sera connectée au backend.'));
function openModal(modal) {
  modal.hidden = false;
  document.body.classList.add('modal-open');
  modal.querySelector('input, select, button').focus();
}
function closeModal(modal) {
  modal.hidden = true;
  if (!document.querySelector('.modal-backdrop:not([hidden])')) document.body.classList.remove('modal-open');
}
document.querySelector('#add-user-button').addEventListener('click', () => openModal(createModal));
table.addEventListener('click', event => {
  const button = event.target.closest('.row-action');
  if (button) {
    userToDelete = button.dataset.user;
    deleteUserName.textContent = userToDelete;
    openModal(deleteModal);
  }
});
document.querySelectorAll('.modal-close, .modal-cancel').forEach(button => {
  button.addEventListener('click', () => closeModal(button.closest('.modal-backdrop')));
});
document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
  backdrop.addEventListener('click', event => { if (event.target === backdrop) closeModal(backdrop); });
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') document.querySelectorAll('.modal-backdrop:not([hidden])').forEach(closeModal);
});
createForm.addEventListener('submit', event => {
  event.preventDefault();
  const data = new FormData(createForm);
  const name = data.get('name').trim();
  const email = data.get('email').trim();
  const role = data.get('role');
  const status = data.get('status');
  const initials = name.split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
  users.unshift({name, email, initials, role, roleLabel: roleLabels[role], date:'Aujourd’hui', status, statusLabel:statusLabels[status], activity:'Jamais', color:''});
  createForm.reset();
  closeModal(createModal);
  renderUsers();
  showToast(`Le compte de ${name} a été ajouté à l’aperçu.`);
});
document.querySelector('#confirm-delete-button').addEventListener('click', () => {
  const index = users.findIndex(user => user.name === userToDelete);
  if (index !== -1) users.splice(index, 1);
  closeModal(deleteModal);
  renderUsers();
  showToast(`Le compte de ${userToDelete} a été supprimé de l’aperçu.`);
  userToDelete = null;
});

const sidebar = document.querySelector('#sidebar');
const menuToggle = document.querySelector('.menu-toggle');
const closeSidebar = () => { sidebar.classList.remove('open'); menuToggle.setAttribute('aria-expanded', 'false'); };
menuToggle.addEventListener('click', () => { const isOpen = sidebar.classList.toggle('open'); menuToggle.setAttribute('aria-expanded', String(isOpen)); });
document.querySelector('.sidebar-close').addEventListener('click', closeSidebar);
document.querySelectorAll('.sidebar .nav-link').forEach(link => link.addEventListener('click', closeSidebar));

renderUsers();
