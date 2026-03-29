export type ColorMode = 'light' | 'dark';

const STORAGE_KEY = 'app-ui-color-mode';

declare global {
  interface Window {
    initMode: () => ColorMode;
    setMode: (mode: ColorMode) => ColorMode;
  }
}

export function setMode(mode: ColorMode): ColorMode {
  document.documentElement.setAttribute('data-bs-theme', mode);
  localStorage.setItem(STORAGE_KEY, mode);
  return mode;
}

export function initMode(): ColorMode {
  try {
    const clientMode = localStorage.getItem(STORAGE_KEY);
    if (clientMode === 'light' || clientMode === 'dark') {
      return setMode(clientMode);
    }

    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return setMode('dark');
    }

    if (window.matchMedia('(prefers-color-scheme: light)').matches) {
      return setMode('light');
    }
  } catch (error) {
    console.error(error);
  }

  return setMode('light');
}

window.setMode = setMode;
window.initMode = initMode;
