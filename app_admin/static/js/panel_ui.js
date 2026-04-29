(function () {
  document.addEventListener('click', (event) => {
    const dismissButton = event.target.closest('[data-dismiss-flash]');
    if (dismissButton) {
      dismissButton.closest('.komunikat')?.remove();
    }
  });
}());
