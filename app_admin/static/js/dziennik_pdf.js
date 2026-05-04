(() => {
  const btn = document.getElementById('btn-pdf');
  if (!btn) return;

  const eid = btn.dataset.enrollmentId;
  const URL_ZLEC    = `/dzienniki/zapis/${eid}/pdf`;
  const URL_STATUS  = (id) => `/dzienniki/zapis/${eid}/pdf/status/${id}`;
  const URL_POBIERZ = (id) => `/dzienniki/zapis/${eid}/pdf/pobierz/${id}`;

  const btnLabel  = document.getElementById('btn-pdf-label');
  const statusEl  = document.getElementById('pdf-status');
  let pollInterval = null;

  function getCsrf() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  }

  function blad(msg) {
    clearInterval(pollInterval);
    btn.disabled = false;
    btnLabel.textContent = 'Pobierz PDF';
    statusEl.textContent = msg;
    statusEl.style.color = 'var(--kolor-blad)';
  }

  function sprawdzStatus(taskId) {
    fetch(URL_STATUS(taskId))
      .then((r) => r.json())
      .then((data) => {
        if (data.status === 'SUCCESS') {
          clearInterval(pollInterval);
          statusEl.textContent = 'Gotowe!';
          btnLabel.textContent = 'Pobierz PDF';
          btn.disabled = false;
          window.location.href = URL_POBIERZ(taskId);
        } else if (data.status === 'FAILURE') {
          clearInterval(pollInterval);
          blad('Błąd kompilacji: ' + (data.error || 'sprawdź logi workera'));
        } else {
          statusEl.textContent = `Kompilacja... ${data.progress || 0}%`;
        }
      })
      .catch(() => {});
  }

  function zlecPDF() {
    btn.disabled = true;
    btnLabel.textContent = 'Generowanie...';
    statusEl.style.display = 'inline';
    statusEl.textContent = 'Zlecam generowanie PDF...';

    fetch(URL_ZLEC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.task_id) {
          statusEl.textContent = 'Kompilacja w toku...';
          pollInterval = setInterval(() => sprawdzStatus(data.task_id), 2000);
        } else {
          blad('Błąd zlecenia: ' + (data.error || 'nieznany'));
        }
      })
      .catch(() => blad('Błąd połączenia z serwerem.'));
  }

  btn.addEventListener('click', zlecPDF);
})();
