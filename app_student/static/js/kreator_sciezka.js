(function () {
  const stepLabels = {
    STANDARD: ['2. Miejsce praktyki', '3. Harmonogram', '4. Wysłanie'],
    EMPLOYMENT: ['2. Wniosek', '3. Komisja', '4. Dyrektor'],
  };

  const previews = {
    STANDARD: 'Ścieżka A: Odbędziesz praktykę w zakładzie pracy na podstawie porozumienia z uczelnią. Wymagane: Porozumienie (zał. 1), Program (zał. 2), Indywidualny Program (zał. 2a). Po zakończeniu: Dziennik praktyki (zał. 6), Sprawozdanie (zał. 7), Potwierdzenie efektów uczenia się (zał. 4).',
    EMPLOYMENT: 'Ścieżka B: Złożysz wniosek (zał. 4b) o uznanie trzynastu efektów uczenia się na podstawie doświadczenia zawodowego. Komisja ds. praktyk wyda opinię (zał. 4a), a Dyrektor Instytutu podejmie ostateczną decyzję. Wybierz poniżej rodzaj zatrudnienia - od tego zależy, jakie dokumenty musisz dołączyć.',
  };

  function updateStepBar(value) {
    const labels = stepLabels[value] || ['2. -', '3. -', '4. -'];
    const stepBar = document.getElementById('pasek-krokow');
    if (!stepBar) return;

    const steps = stepBar.querySelectorAll('.kreator-krok');
    if (steps[1]) steps[1].textContent = labels[0];
    if (steps[2]) steps[2].textContent = labels[1];
    if (steps[3]) steps[3].textContent = labels[2];
  }

  function updateButton() {
    const trackInput = document.getElementById('selected_track');
    const subtypeInput = document.getElementById('selected_subtype');
    const button = document.getElementById('btn-dalej');
    if (!trackInput || !subtypeInput || !button) return;

    const track = trackInput.value;
    const subtype = subtypeInput.value;
    const isEnabled = track === 'STANDARD' || (track === 'EMPLOYMENT' && subtype);
    button.disabled = !isEnabled;
    button.classList.toggle('przycisk--aktywny', isEnabled);
    button.setAttribute('aria-disabled', String(!isEnabled));
  }

  function selectTrack(tile) {
    const trackInput = document.getElementById('selected_track');
    const subtypeInput = document.getElementById('selected_subtype');
    const preview = document.getElementById('path-preview');
    const subSection = document.getElementById('path-subtype-section');
    if (!trackInput || !subtypeInput || !preview || !subSection) return;

    document.querySelectorAll('.path-tile').forEach((item) => {
      item.classList.remove('path-tile--selected');
    });
    tile.classList.add('path-tile--selected');

    const value = tile.dataset.value;
    trackInput.value = value;
    updateStepBar(value);
    preview.textContent = previews[value] || '';
    preview.classList.toggle('u-csp-094', !previews[value]);

    if (value === 'EMPLOYMENT') {
      subSection.classList.remove('u-csp-311');
    } else {
      subSection.classList.add('u-csp-311');
      subtypeInput.value = '';
      document.querySelectorAll('.kafelek-sub').forEach((item) => item.classList.remove('aktywny'));
    }
    updateButton();
  }

  function selectSubtype(tile) {
    const subtypeInput = document.getElementById('selected_subtype');
    if (!subtypeInput) return;

    document.querySelectorAll('.kafelek-sub').forEach((item) => item.classList.remove('aktywny'));
    tile.classList.add('aktywny');
    subtypeInput.value = tile.dataset.sub;
    updateButton();
  }

  function bindKeyboardActivation(tile, callback) {
    tile.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        callback(tile);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.path-tile').forEach((tile) => {
      tile.addEventListener('click', () => selectTrack(tile));
      bindKeyboardActivation(tile, selectTrack);
    });

    document.querySelectorAll('.kafelek-sub').forEach((tile) => {
      tile.addEventListener('click', () => selectSubtype(tile));
      bindKeyboardActivation(tile, selectSubtype);
    });

    const currentTrack = document.getElementById('selected_track')?.value;
    if (currentTrack) {
      const currentTile = document.querySelector(`[data-value="${currentTrack}"]`);
      if (currentTile) selectTrack(currentTile);
    } else {
      updateStepBar('');
      updateButton();
    }
  });
}());
