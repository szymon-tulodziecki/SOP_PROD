// Tłumaczenia dla skryptów — czyta słownik z tagu <script type="application/json" id="js-i18n">.
// Klucz = polski tekst źródłowy; brak wpisu = fallback do polskiego (jak t() w backendzie).
(function () {
  var dict = {};
  var node = document.getElementById('js-i18n');
  if (node) {
    try { dict = JSON.parse(node.textContent) || {}; } catch (e) { dict = {}; }
  }
  window.jsT = function (key) {
    return Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : key;
  };
})();
