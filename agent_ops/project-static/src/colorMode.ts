export type ColorMode = 'light' | 'dark';
export type ColorModePreference = ColorMode | 'system';

const STORAGE_KEY = 'app-ui-color-mode';

declare global {
  interface Window {
    initMode: (preferredMode?: ColorModePreference) => ColorMode;
    setMode: (mode: ColorMode) => ColorMode;
  }
}

function applyMode(mode: ColorMode): ColorMode {
  document.documentElement.setAttribute('data-bs-theme', mode);

  if (document.body) {
    document.body.setAttribute('data-bs-theme', mode);
    return mode;
  }

  document.addEventListener(
    'DOMContentLoaded',
    () => {
      document.body?.setAttribute('data-bs-theme', mode);
    },
    { once: true },
  );

  return mode;
}

function getSystemMode(): ColorMode {
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }

  if (window.matchMedia('(prefers-color-scheme: light)').matches) {
    return 'light';
  }

  return 'light';
}

function getStoredModePreference(): ColorModePreference | undefined {
  try {
    const storedMode = window.localStorage.getItem(STORAGE_KEY);
    if (storedMode === 'light' || storedMode === 'dark' || storedMode === 'system') {
      return storedMode;
    }
  } catch (error) {
    console.error(error);
  }

  return undefined;
}

function storeModePreference(preference: ColorModePreference): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, preference);
  } catch (error) {
    console.error(error);
  }
}

function resolveModePreference(preferredMode?: ColorModePreference): ColorModePreference {
  if (preferredMode === 'light' || preferredMode === 'dark' || preferredMode === 'system') {
    return preferredMode;
  }

  return getStoredModePreference() ?? 'system';
}

export function setMode(mode: ColorMode): ColorMode {
  storeModePreference(mode);
  return applyMode(mode);
}

export function initMode(preferredMode?: ColorModePreference): ColorMode {
  try {
    const resolvedPreference = resolveModePreference(preferredMode);
    storeModePreference(resolvedPreference);

    if (resolvedPreference === 'light' || resolvedPreference === 'dark') {
      return applyMode(resolvedPreference);
    }

    return applyMode(getSystemMode());
  } catch (error) {
    console.error(error);
  }

  return applyMode(preferredMode === 'dark' ? 'dark' : getSystemMode());
}

window.setMode = setMode;
window.initMode = initMode;
