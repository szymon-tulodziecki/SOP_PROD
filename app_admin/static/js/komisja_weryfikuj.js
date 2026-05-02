(function () {
  function setNotesState(outcomeId, isPartial) {
    var notesRow = document.getElementById('notes_row_' + outcomeId);
    if (!notesRow) return;

    notesRow.classList.toggle('u-row-hidden', !isPartial);

    var textarea = notesRow.querySelector('textarea');
    if (!textarea) return;
    textarea.required = isPartial;
    if (!isPartial) textarea.value = '';
  }

  function updateOutcomeGroup(radio) {
    var checked = document.querySelector('input[name="' + radio.name + '"]:checked');
    setNotesState(radio.dataset.outcome, checked && checked.value === 'PARTIALLY_ACHIEVED');
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.radio-efekt').forEach(function (radio) {
      radio.addEventListener('change', function () {
        updateOutcomeGroup(radio);
      });
      updateOutcomeGroup(radio);
    });
  });
})();
