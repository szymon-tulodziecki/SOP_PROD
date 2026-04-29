(function () {
  document.addEventListener('click', (event) => {
    const dismissButton = event.target.closest('[data-dismiss-flash]');
    if (dismissButton) {
      dismissButton.closest('.komunikat')?.remove();
      return;
    }

    const submitButton = event.target.closest('[data-submit-form]');
    if (submitButton) {
      const formId = submitButton.dataset.submitForm;
      document.getElementById(formId)?.submit();
    }
  });
}());
