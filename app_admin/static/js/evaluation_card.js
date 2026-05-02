(() => {
  function parseGrade(input) {
    if (!input || !input.value) return 0;
    const value = Number.parseFloat(String(input.value).replace(',', '.'));
    if (!Number.isFinite(value)) return 0;
    if (value < 2 || value > 5) return 0;
    if (Math.abs(value * 2 - Math.round(value * 2)) > 0.001) return 0;
    return value;
  }

  function roundHalf(value) {
    return Math.round(value * 2) / 2;
  }

  function initEvaluationCard() {
    const root = document.querySelector('[data-evaluation-card]');
    if (!root) return;

    const isPathB = root.dataset.pathB === 'true';
    const p1 = document.querySelector('[name="sprawdzian_ocena_1"]');
    const p2 = document.querySelector('[name="sprawdzian_ocena_2"]');
    const p3 = document.querySelector('[name="sprawdzian_ocena_3"]');
    const os = document.querySelector('[name="ocena_sprawozdania"]');
    const ou = document.querySelector('[name="ocena_uopz"]');
    const oz = document.querySelector('[name="ocena_zopz"]');

    const we = document.getElementById('wynik-e');
    const wk = document.getElementById('wynik-k');
    const btnZakoncz = document.getElementById('btn-zakoncz');
    const ostrzezenie = document.getElementById('ostrzezenie-z');
    if (!we || !wk || !btnZakoncz || !ostrzezenie) return;

    function calculate() {
      const e1 = parseGrade(p1);
      const e2 = parseGrade(p2);
      const e3 = parseGrade(p3);
      const s = parseGrade(os);
      const u = parseGrade(ou);
      const z = parseGrade(oz);

      const examGrades = [e1, e2, e3].filter((grade) => grade >= 2 && grade <= 5);
      const examAverage = examGrades.length
        ? examGrades.reduce((sum, grade) => sum + grade, 0) / examGrades.length
        : 0;

      we.textContent = examAverage > 0 ? examAverage.toFixed(2) : '-';

      const canCalculate = isPathB
        ? examAverage > 0 && s > 0
        : examAverage > 0 && s > 0 && u > 0 && z > 0;

      if (!canCalculate) {
        wk.textContent = '-';
        wk.style.color = 'var(--kolor-glowny)';
        btnZakoncz.disabled = true;
        ostrzezenie.style.display = 'inline-block';
        return;
      }

      const rawFinal = isPathB
        ? 0.9 * examAverage + 0.1 * s
        : 0.4 * examAverage + 0.1 * s + 0.2 * u + 0.3 * z;
      const finalGrade = roundHalf(rawFinal);

      wk.textContent = finalGrade.toFixed(1);
      wk.style.color = finalGrade >= 3.0 ? 'var(--kolor-sukces)' : 'var(--kolor-blad)';
      btnZakoncz.disabled = false;
      ostrzezenie.style.display = 'none';
    }

    [p1, p2, p3, os, ou, oz].filter(Boolean).forEach((input) => {
      input.addEventListener('input', calculate);
      input.addEventListener('change', calculate);
    });

    calculate();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEvaluationCard);
  } else {
    initEvaluationCard();
  }
})();
