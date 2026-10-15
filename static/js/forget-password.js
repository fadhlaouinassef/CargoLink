const forgetForm = document.querySelector('#forget-form');
const forgetStatus = document.querySelector('#forget-status');

forgetForm.addEventListener('submit', event => {
  event.preventDefault();
  forgetStatus.hidden = false;
  forgetForm.querySelector('.submit-button').disabled = true;
});
