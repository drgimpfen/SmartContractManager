/**
 * Reusable Combobox Dropdown Helper
 * Works with Bootstrap 5 .combobox-container containing .combobox-input and .combobox-toggle
 */
(function () {
  'use strict';

  function getComboboxContainer(el) {
    return el.closest('.combobox-container') || el.closest('.input-group') || el.parentElement;
  }

  // Open dropdown when clicking into the input field
  document.addEventListener('click', function (e) {
    const input = e.target.closest('.combobox-input');
    if (!input) return;

    const container = getComboboxContainer(input);
    if (!container) return;

    const toggleBtn = container.querySelector('[data-bs-toggle="dropdown"]');
    if (toggleBtn && window.bootstrap && window.bootstrap.Dropdown) {
      const dropdown = window.bootstrap.Dropdown.getOrCreateInstance(toggleBtn);
      const menu = container.querySelector('.dropdown-menu');
      if (menu && !menu.classList.contains('show')) {
        dropdown.show();
      }
    }
  });

  // Handle selection from dropdown menu
  document.addEventListener('click', function (e) {
    const item = e.target.closest('.combobox-select-item');
    if (!item) return;

    e.preventDefault();
    const container = getComboboxContainer(item);
    if (!container) return;

    const input = container.querySelector('.combobox-input') || container.querySelector('input');
    if (!input) return;

    const value = item.dataset.value !== undefined ? item.dataset.value : item.textContent.trim();
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.focus();

    // Close dropdown explicitly
    const toggleBtn = container.querySelector('[data-bs-toggle="dropdown"]');
    if (toggleBtn && window.bootstrap && window.bootstrap.Dropdown) {
      const dropdown = window.bootstrap.Dropdown.getInstance(toggleBtn);
      if (dropdown) {
        dropdown.hide();
      }
    }
  });

  // When dropdown opens, highlight matching value and show all options
  document.addEventListener('show.bs.dropdown', function (e) {
    const toggleBtn = e.target;
    const container = getComboboxContainer(toggleBtn);
    if (!container) return;

    const input = container.querySelector('.combobox-input');
    const menu = container.querySelector('.dropdown-menu');
    if (!input || !menu) return;

    const val = input.value.trim().toLowerCase();
    const items = menu.querySelectorAll('.combobox-select-item');
    items.forEach(function (btn) {
      const li = btn.closest('li');
      if (li) li.style.display = '';
      const itemVal = (btn.dataset.value || btn.textContent).trim().toLowerCase();
      if (val && itemVal === val) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    menu.querySelectorAll('.dropdown-header, .dropdown-divider').forEach(function (el) {
      const target = el.tagName === 'LI' ? el : el.closest('li') || el;
      target.style.display = '';
    });
  });

  // Filter options when user types into the input
  document.addEventListener('input', function (e) {
    if (!e.target.matches('.combobox-input')) return;

    const container = getComboboxContainer(e.target);
    if (!container) return;

    const menu = container.querySelector('.dropdown-menu');
    const toggleBtn = container.querySelector('[data-bs-toggle="dropdown"]');
    if (!menu) return;

    // Show dropdown if hidden when user types
    if (toggleBtn && window.bootstrap && window.bootstrap.Dropdown && !menu.classList.contains('show')) {
      const dropdown = window.bootstrap.Dropdown.getOrCreateInstance(toggleBtn);
      dropdown.show();
    }

    const filter = e.target.value.toLowerCase().trim();
    const items = menu.querySelectorAll('.combobox-select-item');

    items.forEach(function (btn) {
      const text = (btn.dataset.value || btn.textContent).toLowerCase();
      const matches = !filter || text.includes(filter);
      const li = btn.closest('li');
      if (li) li.style.display = matches ? '' : 'none';
    });

    // Toggle section headers if all their items are hidden
    menu.querySelectorAll('.dropdown-header').forEach(function (header) {
      let next = header.tagName === 'LI' ? header.nextElementSibling : header.closest('li')?.nextElementSibling;
      let hasVisible = false;
      while (next && !next.querySelector?.('.dropdown-header') && !next.classList.contains('dropdown-header') && !next.querySelector?.('.dropdown-divider')) {
        if (next.style.display !== 'none') {
          hasVisible = true;
          break;
        }
        next = next.nextElementSibling;
      }
      const headerLi = header.tagName === 'LI' ? header : header.closest('li') || header;
      headerLi.style.display = (!filter || hasVisible) ? '' : 'none';
    });
  });
})();
