import type { ColorMode } from './colorMode';

declare global {
  interface Window {
    setMode?: (mode: ColorMode) => ColorMode;
  }
}

export function initThemeToggle(): void {
  document.querySelectorAll<HTMLElement>('.color-mode-toggle').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();

      const currentMode = document.documentElement.getAttribute('data-bs-theme') === 'dark'
        ? 'dark'
        : 'light';
      const nextMode: ColorMode = currentMode === 'dark' ? 'light' : 'dark';

      window.setMode?.(nextMode);
    });
  });
}
