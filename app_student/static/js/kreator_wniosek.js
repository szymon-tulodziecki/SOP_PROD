(function () {
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function setStatus(message, color) {
    var status = document.getElementById('upload-status');
    if (!status) return;
    status.textContent = message;
    status.style.color = color;
  }

  function updateCounter() {
    var textarea = document.getElementById('uzasadnienie_input');
    var counter = document.getElementById('uzasadnienie_licznik');
    if (!textarea || !counter) return;
    var count = textarea.value.length;
    counter.textContent = count + ' / min. 500 znakow';
    counter.style.color = count < 500 ? '#dc2626' : 'var(--kolor-tekst-trzeciorzed)';
  }

  function deleteUrl(uploadRoot, documentId) {
    return uploadRoot.dataset.deleteUrlTemplate.replace(
      '00000000-0000-0000-0000-000000000000',
      documentId
    );
  }

  function renderFiles(files, uploadRoot) {
    var list = document.getElementById('upload-lista');
    if (!list) return;
    list.replaceChildren();

    files.forEach(function (file) {
      var row = document.createElement('div');
      row.className = 'upload-plik';

      var label = document.createElement('span');
      label.className = 'u-csp-334';
      label.textContent = file.name + ' (' + file.type + ')';

      var button = document.createElement('button');
      button.className = 'u-csp-336';
      button.type = 'button';
      button.title = 'Usun plik';
      button.setAttribute('aria-label', 'Usun plik');
      button.textContent = 'x';
      button.addEventListener('click', function () {
        removeFile(file.id, files, uploadRoot);
      });

      row.append(label, button);
      list.appendChild(row);
    });
  }

  async function loadExistingFiles(files, uploadRoot) {
    try {
      var response = await fetch(uploadRoot.dataset.listUrl, {
        headers: { 'Accept': 'application/json' }
      });
      if (!response.ok) return;
      var docs = await response.json();
      files.splice(0, files.length);
      docs.forEach(function (doc) {
        files.push({
          id: doc.id,
          name: doc.original_filename,
          type: doc.document_type
        });
      });
      renderFiles(files, uploadRoot);
    } catch (error) {
      setStatus('Nie udalo sie pobrac listy zalacznikow.', '#dc2626');
    }
  }

  async function uploadFile(files, uploadRoot) {
    var fileInput = document.getElementById('upload-file');
    var typeSelect = document.getElementById('upload-type');
    if (!fileInput || !typeSelect) return;

    if (!fileInput.files.length) {
      setStatus('Wybierz plik.', '#dc2626');
      return;
    }

    var formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('document_type', typeSelect.value);
    formData.append('csrf_token', csrfToken());

    setStatus('Wysylanie...', '#6b7280');

    try {
      var response = await fetch(uploadRoot.dataset.uploadUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken() },
        body: formData
      });
      var data = await response.json();

      if (!response.ok) {
        setStatus('Blad: ' + (data.error || 'Nie udalo sie przeslac.'), '#dc2626');
        return;
      }

      files.push({
        id: data.document_id,
        name: fileInput.files[0].name,
        type: typeSelect.options[typeSelect.selectedIndex].text
      });
      renderFiles(files, uploadRoot);
      fileInput.value = '';
      var fileLabel = document.getElementById('upload-file-label');
      if (fileLabel) fileLabel.textContent = 'Wybierz plik PDF lub przeciagnij tutaj';
      setStatus('Plik dodany pomyslnie.', '#059669');
    } catch (error) {
      setStatus('Blad polaczenia.', '#dc2626');
    }
  }

  async function removeFile(documentId, files, uploadRoot) {
    var formData = new FormData();
    formData.append('csrf_token', csrfToken());

    try {
      var response = await fetch(deleteUrl(uploadRoot, documentId), {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken() },
        body: formData
      });
      if (!response.ok) {
        setStatus('Nie udalo sie usunac pliku.', '#dc2626');
        return;
      }
      var index = files.findIndex(function (file) { return file.id === documentId; });
      if (index >= 0) files.splice(index, 1);
      renderFiles(files, uploadRoot);
      setStatus('Plik usuniety.', '#059669');
    } catch (error) {
      setStatus('Blad polaczenia.', '#dc2626');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var uploadRoot = document.getElementById('wniosek-upload');
    if (!uploadRoot) return;

    var files = [];
    var textarea = document.getElementById('uzasadnienie_input');
    var fileInput = document.getElementById('upload-file');
    var uploadButton = document.getElementById('upload-submit');
    var fileLabel = document.getElementById('upload-file-label');

    if (textarea) {
      textarea.addEventListener('input', updateCounter);
      updateCounter();
    }
    if (fileInput && fileLabel) {
      fileInput.addEventListener('change', function () {
        fileLabel.textContent = fileInput.files[0] ? fileInput.files[0].name : 'Wybierz plik PDF';
      });
    }
    if (uploadButton) {
      uploadButton.addEventListener('click', function () {
        uploadFile(files, uploadRoot);
      });
    }

    loadExistingFiles(files, uploadRoot);
  });
})();
