// Wzajemnie wyklucza ADMIN z pozostałymi rolami w formularzu pracownika.
(function () {
  const boxes = document.querySelectorAll('input[type="checkbox"][name="roles"]');
  if (!boxes.length) return;

  function sync() {
    const checked = Array.from(boxes).filter(b => b.checked).map(b => b.value);
    const adminOn = checked.includes('ADMIN');
    const otherOn = checked.some(v => v !== 'ADMIN');

    boxes.forEach(b => {
      let disable = false;
      if (b.value === 'ADMIN' && otherOn) disable = true;
      if (b.value !== 'ADMIN' && adminOn) disable = true;
      b.disabled = disable;
      b.closest('.role-checkbox-pozycja').classList.toggle('is-disabled', disable);
    });
  }

  boxes.forEach(b => b.addEventListener('change', sync));
  sync();
})();
