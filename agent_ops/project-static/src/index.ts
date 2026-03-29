import { initMessages } from './messages';
import { initThemeToggle } from './themeToggle';

function initUi(): void {
  initThemeToggle();
  initMessages();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initUi, { once: true });
} else {
  initUi();
}
