type Point = {
  x: number;
  y: number;
};

export type ViewportState = {
  x: number;
  y: number;
  zoom: number;
};

type Bounds = {
  height: number;
  minX: number;
  minY: number;
  width: number;
};

const MIN_ZOOM = 0.45;
const MAX_ZOOM = 1.8;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function normalizeViewport(viewport: ViewportState | undefined): ViewportState {
  return {
    x: Number.isFinite(viewport?.x) ? viewport!.x : 0,
    y: Number.isFinite(viewport?.y) ? viewport!.y : 0,
    zoom: clamp(Number.isFinite(viewport?.zoom) ? viewport!.zoom : 1, MIN_ZOOM, MAX_ZOOM),
  };
}

export function createViewportController(params: {
  board: HTMLElement;
  onChange?: (viewport: ViewportState) => void;
  surface: HTMLElement;
  viewport?: ViewportState;
}) {
  const { board, onChange, surface } = params;
  let viewport = normalizeViewport(params.viewport);

  function emitChange(): void {
    onChange?.(viewport);
  }

  function apply(): void {
    surface.style.transform = `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`;
  }

  function setViewport(nextViewport: ViewportState, options?: { silent?: boolean }): void {
    viewport = normalizeViewport(nextViewport);
    apply();
    if (!options?.silent) {
      emitChange();
    }
  }

  function getBoardLocalPoint(clientX: number, clientY: number): Point {
    const boardRect = board.getBoundingClientRect();
    return {
      x: clientX - boardRect.left,
      y: clientY - boardRect.top,
    };
  }

  function screenToWorld(clientX: number, clientY: number): Point {
    const localPoint = getBoardLocalPoint(clientX, clientY);
    return {
      x: (localPoint.x - viewport.x) / viewport.zoom,
      y: (localPoint.y - viewport.y) / viewport.zoom,
    };
  }

  function worldToScreen(point: Point): Point {
    return {
      x: viewport.x + point.x * viewport.zoom,
      y: viewport.y + point.y * viewport.zoom,
    };
  }

  function panBy(deltaX: number, deltaY: number): void {
    setViewport({
      ...viewport,
      x: viewport.x + deltaX,
      y: viewport.y + deltaY,
    });
  }

  function zoomAt(clientX: number, clientY: number, deltaZoom: number): void {
    const localPoint = getBoardLocalPoint(clientX, clientY);
    const worldPoint = screenToWorld(clientX, clientY);
    const nextZoom = clamp(viewport.zoom + deltaZoom, MIN_ZOOM, MAX_ZOOM);

    setViewport({
      x: localPoint.x - worldPoint.x * nextZoom,
      y: localPoint.y - worldPoint.y * nextZoom,
      zoom: nextZoom,
    });
  }

  function zoomByStep(direction: 'in' | 'out'): void {
    const boardRect = board.getBoundingClientRect();
    zoomAt(
      boardRect.left + board.clientWidth / 2,
      boardRect.top + board.clientHeight / 2,
      direction === 'in' ? 0.12 : -0.12,
    );
  }

  function fitBounds(bounds: Bounds | null, options?: { padding?: number }): void {
    if (!bounds || bounds.width <= 0 || bounds.height <= 0) {
      setViewport({ x: 0, y: 0, zoom: 1 });
      return;
    }

    const padding = options?.padding ?? 88;
    const availableWidth = Math.max(board.clientWidth - padding * 2, 1);
    const availableHeight = Math.max(board.clientHeight - padding * 2, 1);
    const zoom = clamp(
      Math.min(availableWidth / bounds.width, availableHeight / bounds.height),
      MIN_ZOOM,
      MAX_ZOOM,
    );

    setViewport({
      x: (board.clientWidth - bounds.width * zoom) / 2 - bounds.minX * zoom,
      y: (board.clientHeight - bounds.height * zoom) / 2 - bounds.minY * zoom,
      zoom,
    });
  }

  function focusPoint(point: Point): void {
    setViewport({
      ...viewport,
      x: board.clientWidth / 2 - point.x * viewport.zoom,
      y: board.clientHeight / 2 - point.y * viewport.zoom,
    });
  }

  apply();

  return {
    apply,
    fitBounds,
    focusPoint,
    getBoardLocalPoint,
    getViewport(): ViewportState {
      return { ...viewport };
    },
    panBy,
    screenToWorld,
    setViewport,
    worldToScreen,
    zoomAt,
    zoomByStep,
  };
}
