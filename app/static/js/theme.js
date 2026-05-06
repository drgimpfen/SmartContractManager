const themeToggle = document.getElementById('themeToggle');
const root = document.documentElement;

function setTheme(theme) {
  root.setAttribute('data-bs-theme', theme);
  root.setAttribute('data-theme', theme);
  localStorage.setItem('smartcontract-theme', theme);
}

const savedTheme = localStorage.getItem('smartcontract-theme');
if (savedTheme) {
  setTheme(savedTheme);
}

if (themeToggle) {
  themeToggle.addEventListener('click', () => {
    const current = root.getAttribute('data-bs-theme') || 'light';
    setTheme(current === 'light' ? 'dark' : 'light');
  });
}
