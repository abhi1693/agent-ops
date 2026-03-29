type ToastLike = {
  show(): void;
};

type ToastConstructor = new (element: Element) => ToastLike;

declare global {
  interface Window {
    Toast?: ToastConstructor;
  }
}

export function initMessages(): void {
  if (!window.Toast) {
    return;
  }

  document.querySelectorAll('#django-messages .toast').forEach((element) => {
    new window.Toast!(element).show();
  });
}
