(function () {
  document.addEventListener('click', (event) => {
    const dismissButton = event.target.closest('[data-dismiss-flash]');
    if (dismissButton) {
      dismissButton.closest('.komunikat')?.remove();
      return;
    }

    const expandButton = event.target.closest('.btn-rozwin');
    if (expandButton) {
      const shortDescription = expandButton.closest('.opis-skrot');
      if (shortDescription) {
        const fullDescription = shortDescription.nextElementSibling;
        shortDescription.style.display = 'none';
        if (fullDescription?.classList.contains('opis-pelny')) {
          fullDescription.classList.remove('u-csp-094');
          fullDescription.style.display = '';
        }
        return;
      }

      const fullDescription = expandButton.closest('.opis-pelny');
      if (fullDescription) {
        const previousShortDescription = fullDescription.previousElementSibling;
        fullDescription.classList.add('u-csp-094');
        fullDescription.style.display = 'none';
        if (previousShortDescription?.classList.contains('opis-skrot')) {
          previousShortDescription.style.display = '';
        }
        return;
      }
    }

    const submitButton = event.target.closest('[data-submit-form]');
    if (submitButton) {
      const formId = submitButton.dataset.submitForm;
      document.getElementById(formId)?.submit();
    }
  });
}());
