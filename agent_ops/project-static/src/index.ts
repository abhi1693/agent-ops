import { initMessages } from './messages';

const LEGACY_UI_STORAGE_KEYS = ['app-ui-object-depth', 'app-ui-dmlldw==', 'app-ui-secret'] as const;

function purgeLegacyUiStorage(): void {
  try {
    LEGACY_UI_STORAGE_KEYS.forEach((key) => {
      window.localStorage.removeItem(key);
    });
  } catch (error) {
    console.error(error);
  }
}

function initUi(): void {
  purgeLegacyUiStorage();
  initMessages();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initUi, { once: true });
} else {
  initUi();
}
