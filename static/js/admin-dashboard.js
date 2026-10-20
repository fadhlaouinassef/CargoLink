const sidebar = document.querySelector('#sidebar');
const menuToggle = document.querySelector('.menu-toggle');
const closeSidebar = document.querySelector('.sidebar-close');

if (sidebar && menuToggle) {
  menuToggle.addEventListener('click', () => {
    const isOpen = sidebar.classList.toggle('open');
    menuToggle.setAttribute('aria-expanded', String(isOpen));
  });
}

if (closeSidebar && menuToggle && sidebar) {
  closeSidebar.addEventListener('click', () => {
    sidebar.classList.remove('open');
    menuToggle.setAttribute('aria-expanded', 'false');
  });
}

const createModal = document.querySelector('#create-user-modal');
const deleteModal = document.querySelector('#delete-user-modal');
const deleteForm = document.querySelector('#delete-user-form');
const deleteUserName = document.querySelector('#delete-user-name');

function openModal(modal) {
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add('modal-open');
  const firstField = modal.querySelector('input, select, button');
  if (firstField) firstField.focus();
}

function closeModal(modal) {
  if (!modal) return;
  modal.hidden = true;
  if (!document.querySelector('.modal-backdrop:not([hidden])')) {
    document.body.classList.remove('modal-open');
  }
}

document.querySelector('#add-user-button')?.addEventListener('click', () => openModal(createModal));

document.querySelectorAll('.modal-close, .modal-cancel').forEach(button => {
  button.addEventListener('click', () => closeModal(button.closest('.modal-backdrop')));
});

document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
  backdrop.addEventListener('click', event => {
    if (event.target === backdrop) closeModal(backdrop);
  });
});

document.querySelectorAll('.delete-action').forEach(button => {
  button.addEventListener('click', () => {
    deleteForm.action = button.dataset.deleteUrl;
    deleteUserName.textContent = button.dataset.userName;
    openModal(deleteModal);
  });
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop:not([hidden])').forEach(closeModal);
  }
});
