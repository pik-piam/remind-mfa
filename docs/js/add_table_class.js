document.addEventListener('DOMContentLoaded', function () {
  // find headings with exact text "Parameters"
  var headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
  for (var i = 0; i < headings.length; i++) {
    var h = headings[i];
    if (h.textContent && h.textContent.trim() === 'Parameters') {
      var el = h.nextElementSibling;
      while (el && el.tagName !== 'TABLE') {
        el = el.nextElementSibling;
      }
      if (el && el.tagName === 'TABLE') {
        // wrap table in a div to avoid modifying the table element itself
        if (!el.parentElement.classList.contains('parameters-table-wrap')) {
          var wrapper = document.createElement('div');
          wrapper.className = 'parameters-table-wrap';
          el.parentNode.insertBefore(wrapper, el);
          wrapper.appendChild(el);
        }
      }
      break; // stop after first match
    }
  }
});
