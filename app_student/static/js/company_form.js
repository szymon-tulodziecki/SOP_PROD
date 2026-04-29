(function () {
  function getCompanies() {
    const dataNode = document.getElementById('company-data');
    if (!dataNode) return {};

    try {
      return JSON.parse(dataNode.dataset.companies || '{}');
    } catch (_error) {
      return {};
    }
  }

  function setHidden(element, isHidden) {
    if (!element) return;
    element.classList.toggle('u-csp-094', isHidden);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const companies = getCompanies();
    const typeSelect = document.getElementById('firma_typ');
    const databaseBlock = document.getElementById('blok-baza');
    const customBlock = document.getElementById('blok-custom');
    const companySelect = document.getElementById('firma_id_select');
    const preview = document.getElementById('firma-podglad');

    if (!typeSelect || !databaseBlock || !customBlock) return;

    function toggleCompanyMode() {
      const isDatabase = typeSelect.value === 'database';
      setHidden(databaseBlock, !isDatabase);
      setHidden(customBlock, isDatabase);
    }

    function updatePreview() {
      if (!companySelect || !preview) return;

      const company = companies[companySelect.value];
      if (!company) {
        preview.classList.add('u-csp-094');
        preview.textContent = '';
        return;
      }

      const details = [company.address, company.city].filter(Boolean).join(', ');
      preview.innerHTML = [
        `<strong>${company.name}</strong>`,
        details,
        company.tax_id ? `NIP: ${company.tax_id}` : '',
      ].filter(Boolean).join('<br>');
      preview.classList.remove('u-csp-094');
    }

    typeSelect.addEventListener('change', toggleCompanyMode);
    companySelect?.addEventListener('change', updatePreview);

    toggleCompanyMode();
    updatePreview();
  });
}());
