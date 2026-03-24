async function generujDokument(btnElement, urlGeneruj) {
    const label   = btnElement.querySelector('[data-pdf-label]');
    const spinner = btnElement.querySelector('[data-pdf-spinner]');

    btnElement.disabled = true;
    if (label) label.style.display = 'none';
    if (spinner) {
        spinner.style.display = 'inline';
        spinner.textContent = 'Generowanie...';
    }

    try {
        const csrfToken = document.querySelector('input[name="csrf_token"]').value;

        const resp = await fetch(urlGeneruj, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken }
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
            throw new Error(err.error || 'Nieznany błąd');
        }

        const blob = await resp.blob();
        const url  = URL.createObjectURL(blob);
        const cd   = resp.headers.get('Content-Disposition') || '';
        const m    = cd.match(/filename[^;=\n]*=(['"]?)([^'"\n]+)\1/);
        const filename = m ? m[2] : 'dokument.pdf';

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);

    } catch (err) {
        alert('Błąd generowania PDF: ' + err.message);
    } finally {
        btnElement.disabled = false;
        if (label) label.style.display = 'inline';
        if (spinner) {
            spinner.style.display = 'none';
            spinner.textContent = '';
        }
    }
}

function checkStatus() {
    /* stary kod już nieużywany */
}


async function checkStatus(taskId, btnElement, label, spinner, urlStatusBase) {
    try {
        const resp = await fetch(urlStatusBase + taskId);
        const data = await resp.json();
        
        if (data.status === 'SUCCESS') {
            if (spinner) spinner.textContent = 'Gotowe! Pobieranie...';
            window.location.href = data.download_url;
            
            setTimeout(() => {
                resetButton(btnElement, label, spinner);
            }, 3000);
        } else if (data.status === 'FAILURE') {
            throw new Error(data.error || 'Błąd generowania PDF');
        } else {
            if (spinner) spinner.textContent = `Generowanie... (${data.progress || 0}%)`;
            setTimeout(() => checkStatus(taskId, btnElement, label, spinner, urlStatusBase), 2000);
        }
    } catch (err) {
        alert('Błąd statusu: ' + err.message);
        resetButton(btnElement, label, spinner);
    }
}

function resetButton(btn, label, spinner) {
    btn.disabled = false;
    if (label) label.style.display = 'inline';
    if (spinner) {
        spinner.style.display = 'none';
        spinner.textContent = '';
    }
}