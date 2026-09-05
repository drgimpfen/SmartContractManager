(function () {
  'use strict';

  const FALLBACK_COLORS = [
    "#0d6efd", "#6610f2", "#6f42c1", "#d63384",
    "#fd7e14", "#ffc107", "#198754", "#20c997", "#0dcaf0"
  ];

  function getDeterministicColor(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const idx = Math.abs(hash) % FALLBACK_COLORS.length;
    return FALLBACK_COLORS[idx];
  }

  function initTagPicker(container) {
    if (container.dataset.initialized === 'true') return;
    container.dataset.initialized = 'true';

    const hiddenInput = container.querySelector('.tag-picker-hidden-input');
    const box = container.querySelector('.tag-input-box');
    const textInput = container.querySelector('.tag-inline-input');
    const defaultPlaceholder = textInput ? (textInput.getAttribute('data-placeholder') || 'Tag eingeben...') : 'Tag eingeben...';

    if (!hiddenInput || !box || !textInput) return;

    // Load available tags from data-available-tags
    let availableTags = [];
    try {
      const raw = container.getAttribute('data-available-tags');
      if (raw) {
        availableTags = JSON.parse(raw);
      }
    } catch (e) {
      console.warn('Failed to parse data-available-tags:', e);
      availableTags = [];
    }

    // Load initial tags from hidden input
    let currentTags = hiddenInput.value
      ? hiddenInput.value.split(',').map(t => t.trim()).filter(Boolean)
      : [];

    function getTagColor(name) {
      const found = availableTags.find(t => t.name.toLowerCase() === name.toLowerCase());
      if (found && found.color) return found.color;
      return getDeterministicColor(name);
    }

    // Create dropdown menu element anchored to container
    let dropdownMenu = container.querySelector('.tag-autocomplete-dropdown');
    if (!dropdownMenu) {
      dropdownMenu = document.createElement('ul');
      dropdownMenu.className = 'dropdown-menu w-100 shadow-sm mt-1 tag-autocomplete-dropdown';
      dropdownMenu.style.maxHeight = '220px';
      dropdownMenu.style.overflowY = 'auto';
      dropdownMenu.style.position = 'absolute';
      dropdownMenu.style.top = '100%';
      dropdownMenu.style.left = '0';
      dropdownMenu.style.right = '0';
      dropdownMenu.style.zIndex = '1055';
      container.appendChild(dropdownMenu);
    }

    let activeIndex = -1;

    function renderBadges() {
      // Remove all existing badge elements from box (keep textInput)
      const existingBadges = box.querySelectorAll('.tag-inline-badge');
      existingBadges.forEach(el => el.remove());

      currentTags.forEach((tagName, index) => {
        const badge = document.createElement('span');
        badge.className = 'badge rounded-pill d-inline-flex align-items-center gap-1 py-1 px-2 tag-inline-badge';
        badge.style.backgroundColor = getTagColor(tagName);
        badge.style.color = '#ffffff';
        badge.style.fontSize = '0.75rem';

        const label = document.createElement('span');
        label.textContent = tagName;
        badge.appendChild(label);

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close btn-close-white ms-1';
        closeBtn.style.fontSize = '0.5rem';
        closeBtn.setAttribute('aria-label', `Tag ${tagName} entfernen`);
        closeBtn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          removeTag(index);
          textInput.focus();
        });
        badge.appendChild(closeBtn);

        // Insert badge right before textInput
        box.insertBefore(badge, textInput);
      });

      // Update placeholder
      if (currentTags.length > 0) {
        textInput.placeholder = '+ Weiterer Tag...';
      } else {
        textInput.placeholder = defaultPlaceholder;
      }

      // Update hidden input for form submission
      hiddenInput.value = currentTags.join(', ');
    }

    function addTag(name) {
      const trimmed = name.trim().replace(/,/g, '');
      if (!trimmed) return;
      const exists = currentTags.some(t => t.toLowerCase() === trimmed.toLowerCase());
      if (!exists) {
        currentTags.push(trimmed);
        // If not in availableTags, record it
        if (!availableTags.some(t => t.name.toLowerCase() === trimmed.toLowerCase())) {
          availableTags.push({ name: trimmed, color: getDeterministicColor(trimmed) });
        }
        renderBadges();
      }
    }

    function removeTag(index) {
      currentTags.splice(index, 1);
      renderBadges();
      renderDropdown();
    }

    function showDropdown() {
      renderDropdown();
      dropdownMenu.classList.add('show');
    }

    function hideDropdown() {
      dropdownMenu.classList.remove('show');
      activeIndex = -1;
    }

    function renderDropdown() {
      dropdownMenu.innerHTML = '';
      const query = textInput.value.trim().toLowerCase();

      // Available tags not yet selected
      const unselected = availableTags.filter(
        t => !currentTags.some(ct => ct.toLowerCase() === t.name.toLowerCase())
      );

      // Filtered tags matching query
      const matches = query
        ? unselected.filter(t => t.name.toLowerCase().includes(query))
        : unselected;

      let items = [];

      // Check if query is a new tag (non-empty and does not match any current or existing tag exactly)
      const exactMatch = availableTags.some(t => t.name.toLowerCase() === query) ||
                         currentTags.some(ct => ct.toLowerCase() === query);

      if (query && !exactMatch) {
        // Option to create new tag
        const createLi = document.createElement('li');
        const createBtn = document.createElement('button');
        createBtn.type = 'button';
        createBtn.className = 'dropdown-item d-flex align-items-center gap-2 py-2 px-3 text-primary fw-semibold';
        createBtn.innerHTML = `<i class="bi bi-plus-circle"></i> <span>"${textInput.value.trim()}" neu erstellen</span>`;
        createBtn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          addTag(textInput.value.trim());
          textInput.value = '';
          textInput.focus();
          renderDropdown();
        });
        createLi.appendChild(createBtn);
        dropdownMenu.appendChild(createLi);
        items.push(createBtn);
      }

      matches.forEach(tag => {
        const li = document.createElement('li');
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'dropdown-item d-flex align-items-center justify-content-between py-1 px-3';

        const leftSpan = document.createElement('span');
        leftSpan.className = 'd-flex align-items-center gap-2';

        const dot = document.createElement('span');
        dot.className = 'rounded-circle d-inline-block';
        dot.style.width = '10px';
        dot.style.height = '10px';
        dot.style.backgroundColor = tag.color || getDeterministicColor(tag.name);

        const nameSpan = document.createElement('span');
        nameSpan.textContent = tag.name;

        leftSpan.appendChild(dot);
        leftSpan.appendChild(nameSpan);
        btn.appendChild(leftSpan);

        const plusBadge = document.createElement('span');
        plusBadge.className = 'badge bg-body-secondary text-body-secondary border rounded-pill px-1';
        plusBadge.style.fontSize = '0.65rem';
        plusBadge.textContent = '+';
        btn.appendChild(plusBadge);

        btn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          addTag(tag.name);
          textInput.value = '';
          textInput.focus();
          renderDropdown();
        });

        li.appendChild(btn);
        dropdownMenu.appendChild(li);
        items.push(btn);
      });

      if (items.length === 0) {
        const li = document.createElement('li');
        li.className = 'dropdown-item text-muted disabled small py-2 px-3';
        if (query) {
          li.textContent = 'Keine Treffer';
        } else if (availableTags.length === 0) {
          li.textContent = 'Noch keine Tags vorhanden. Tippen zum Erstellen.';
        } else {
          li.textContent = 'Alle vorhandenen Tags bereits ausgewählt.';
        }
        dropdownMenu.appendChild(li);
      }

      // Keep activeIndex within bounds
      if (items.length > 0) {
        if (activeIndex >= items.length) activeIndex = items.length - 1;
        if (activeIndex >= 0) {
          items[activeIndex].classList.add('active');
        }
      } else {
        activeIndex = -1;
      }
    }

    // Input events
    textInput.addEventListener('input', () => {
      activeIndex = -1;
      showDropdown();
    });

    textInput.addEventListener('focus', () => {
      box.classList.add('focus-ring', 'border-primary');
      box.style.borderColor = 'var(--bs-primary)';
      box.style.boxShadow = '0 0 0 0.25rem rgba(13, 110, 253, 0.15)';
      showDropdown();
    });

    box.addEventListener('click', () => {
      textInput.focus();
      showDropdown();
    });

    // Keyboard navigation
    textInput.addEventListener('keydown', (e) => {
      const items = dropdownMenu.querySelectorAll('button.dropdown-item');

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (!dropdownMenu.classList.contains('show')) {
          showDropdown();
          return;
        }
        if (items.length > 0) {
          if (activeIndex >= 0 && activeIndex < items.length) {
            items[activeIndex].classList.remove('active');
          }
          activeIndex = (activeIndex + 1) % items.length;
          items[activeIndex].classList.add('active');
          items[activeIndex].scrollIntoView({ block: 'nearest' });
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (!dropdownMenu.classList.contains('show')) {
          showDropdown();
          return;
        }
        if (items.length > 0) {
          if (activeIndex >= 0 && activeIndex < items.length) {
            items[activeIndex].classList.remove('active');
          }
          activeIndex = (activeIndex - 1 + items.length) % items.length;
          items[activeIndex].classList.add('active');
          items[activeIndex].scrollIntoView({ block: 'nearest' });
        }
      } else if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        e.stopPropagation();

        if (dropdownMenu.classList.contains('show') && activeIndex >= 0 && items[activeIndex]) {
          items[activeIndex].click();
        } else if (textInput.value.trim()) {
          addTag(textInput.value.trim());
          textInput.value = '';
          renderDropdown();
        }
      } else if (e.key === 'Escape') {
        hideDropdown();
      } else if (e.key === 'Backspace' && textInput.value === '') {
        if (currentTags.length > 0) {
          removeTag(currentTags.length - 1);
        }
      }
    });

    // Close dropdown on outside click
    document.addEventListener('pointerdown', (e) => {
      if (!container.contains(e.target)) {
        hideDropdown();
        box.classList.remove('focus-ring', 'border-primary');
        box.style.borderColor = '';
        box.style.boxShadow = '';
        // If text was left in input when clicking outside, save as tag
        if (textInput.value.trim()) {
          addTag(textInput.value.trim());
          textInput.value = '';
        }
      }
    });

    // Initial render
    renderBadges();
  }

  window.initTagPickers = function () {
    document.querySelectorAll('.tag-picker-inline').forEach(initTagPicker);
  };

  document.addEventListener('DOMContentLoaded', () => {
    window.initTagPickers();
  });

  // Re-initialize when Bootstrap modals are opened
  document.addEventListener('shown.bs.modal', () => {
    window.initTagPickers();
  });
})();
