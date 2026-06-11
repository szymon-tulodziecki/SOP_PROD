/**
 * Generuje dokument PDF. Obsługuje bezpośrednie pobieranie lub ostrzeżenia o brakach danych.
 */
async function generujDokument(btnElement, urlGeneruj, isForced = false) {
    const T = window.jsT || ((s) => s);
    const label = btnElement.querySelector('[data-pdf-label]');
    const spinner = btnElement.querySelector('[data-pdf-spinner]');

    // Blokujemy przycisk i pokazujemy spinner
    btnElement.disabled = true;
    if (label) label.style.display = 'none';
    if (spinner) {
        spinner.style.display = 'inline';
        spinner.textContent = isForced
            ? T('Generowanie wymuszone...')
            : T('Generowanie...');
    }

    try {
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        const csrfToken = csrfMeta ? csrfMeta.content : (document.querySelector('input[name="csrf_token"]')?.value || '');

        // Flaga wymuszenia trafia do ciała POST.
        const resp = await fetch(urlGeneruj, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ force: isForced })
        });

        const contentType = resp.headers.get('content-type') || '';

        // SCENARIUSZ A: Serwer zwraca JSON (błąd lub ostrzeżenie o brakach)
        if (contentType.includes('application/json')) {
            const data = await resp.json();

            // Jeśli serwer prosi o potwierdzenie braków danych
            if (data.requires_confirmation) {
                const listaBrakow = data.warnings.map(w => `• ${w}`).join('\n');
                const userConfirmed = confirm(
                    `${data.message}\n\n${T('Lista brakujących pól:')}\n${listaBrakow}\n\n${T('Czy mimo to wygenerować dokument?')}`
                );

                if (userConfirmed) {
                    // Wywołujemy funkcję ponownie z flagą isForced = true
                    return generujDokument(btnElement, urlGeneruj, true);
                } else {
                    resetButton(btnElement, label, spinner);
                    return;
                }
            }

            // Jeśli to zwykły błąd JSON
            if (data.error) throw new Error(data.error);
        }

        // SCENARIUSZ B: Serwer zwraca plik PDF (Blob)
        if (!resp.ok) throw new Error(`${T('Błąd serwera')}: ${resp.status}`);

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);

        // Wyciągamy nazwę pliku z nagłówka lub ustawiamy domyślną
        const cd = resp.headers.get('Content-Disposition') || '';
        const m = cd.match(/filename[^;=\n]*=(['"]?)([^'"\n]+)\1/);
        const filename = m ? m[2] : 'dokument.pdf';

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();

        // Sprzątanie
        setTimeout(() => {
            a.remove();
            URL.revokeObjectURL(url);
        }, 100);

    } catch (err) {
        alert(`${T('Błąd generowania PDF')}: ${err.message}`);
    } finally {
        // Resetujemy przycisk tylko jeśli nie jesteśmy w trakcie rekurencyjnego wywołania "force"
        if (!isForced || !btnElement.disabled) {
            resetButton(btnElement, label, spinner);
        }
    }
}

/**
 * Przywraca pierwotny stan przycisku.
 */
function resetButton(btn, label, spinner) {
    btn.disabled = false;
    if (label) label.style.display = 'inline';
    if (spinner) {
        spinner.style.display = 'none';
        spinner.textContent = '';
    }
}
