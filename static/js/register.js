const registerForm = document.querySelector('#register-form');
const registerStatus = document.querySelector('#register-status');

registerForm.addEventListener('submit', event => {
  event.preventDefault();
  registerStatus.hidden = false;
  registerForm.querySelector('.submit-button').disabled = true;
});
