(() => {
  function obliczK() {
    const e = parseFloat(document.querySelector('[name="ocena_egzamin"]')?.value) || 0;
    const s = parseFloat(document.querySelector('[name="ocena_sprawozdanie"]')?.value) || 0;
    const u = parseFloat(document.querySelector('[name="supervisor_grade"]')?.value) || 0;
    const z = parseFloat(document.querySelector('[name="workplace_grade"]')?.value) || 0;
    const wynik = document.getElementById('wynik-k');
    if (!wynik) return;
    if (e && s && u && z) {
      const k = (0.4 * e + 0.1 * s + 0.2 * u + 0.3 * z).toFixed(1);
      wynik.textContent = k;
      wynik.style.color = k >= 3.0 ? 'var(--kolor-sukces)' : 'var(--kolor-blad)';
    } else {
      wynik.textContent = '—';
      wynik.style.color = 'var(--kolor-glowny)';
    }
  }

  function init() {
    if (!document.getElementById('wynik-k')) return;
    document.querySelectorAll('select').forEach((s) => s.addEventListener('change', obliczK));
    obliczK();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
