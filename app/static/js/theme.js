(function () {
  'use strict';

  const STORAGE_KEY = 'smartcontract-theme';

  function getStoredTheme() {
    return localStorage.getItem(STORAGE_KEY);
  }

  function getPreferredTheme() {
    const storedTheme = getStoredTheme();
    if (storedTheme) {
      return storedTheme;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function setTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    updateThemeUI(theme);
  }

  function updateThemeUI(theme) {
    const isDark = theme === 'dark';
    
    // Toggle sun/moon icons across all theme buttons
    document.querySelectorAll('.theme-icon-light').forEach(el => {
      el.classList.toggle('d-none', !isDark);
    });
    document.querySelectorAll('.theme-icon-dark').forEach(el => {
      el.classList.toggle('d-none', isDark);
    });
  }

  // Initialize theme immediately to prevent flashing
  const currentTheme = getPreferredTheme();
  setTheme(currentTheme);

  window.addEventListener('DOMContentLoaded', () => {
    updateThemeUI(getPreferredTheme());

    document.querySelectorAll('.theme-toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const activeTheme = document.documentElement.getAttribute('data-bs-theme') || 'light';
        const newTheme = activeTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
      });
    });

    // Listen for OS color scheme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      const stored = getStoredTheme();
      if (!stored) {
        setTheme(getPreferredTheme());
      }
    });
  });
})();
