export type BrowserElements = {
  backButton: HTMLButtonElement;
  browser: HTMLElement;
  browserContent: HTMLElement;
  browserDescription: HTMLElement;
  browserEmpty: HTMLElement;
  browserTitle: HTMLElement;
  openButton: HTMLButtonElement;
  searchInput: HTMLInputElement;
  searchWrap: HTMLElement;
};

export type CanvasElements = {
  board: HTMLElement;
  definitionInput: HTMLInputElement | HTMLTextAreaElement;
  edgeControls: HTMLElement;
  edgeLayer: SVGSVGElement;
  emptyState: HTMLElement;
  fitViewButton: HTMLButtonElement;
  nodeLayer: HTMLElement;
  nodeMenu: HTMLElement;
  settingsDescription: HTMLElement;
  settingsFields: HTMLElement;
  settingsPanel: HTMLElement;
  settingsTitle: HTMLElement;
  surface: HTMLElement;
  zoomInButton: HTMLButtonElement;
  zoomLabel: HTMLElement;
  zoomOutButton: HTMLButtonElement;
};

export type ExecutionElements = {
  error: HTMLElement;
  nodeRunButton: HTMLButtonElement | null;
  result: HTMLElement;
  resultBadge: HTMLElement;
  resultContext: HTMLElement;
  resultEmpty: HTMLElement;
  resultError: HTMLElement;
  resultOutput: HTMLElement;
  resultSummary: HTMLElement;
  resultTitle: HTMLElement;
  resultTrace: HTMLElement;
  runButton: HTMLButtonElement;
  status: HTMLElement;
};

export function getBrowserElements(root: ParentNode): BrowserElements | null {
  const backButton = root.querySelector<HTMLButtonElement>('[data-node-browser-back]');
  const browser = root.querySelector<HTMLElement>('[data-node-browser]');
  const browserContent = root.querySelector<HTMLElement>('[data-node-browser-content]');
  const browserDescription = root.querySelector<HTMLElement>('[data-node-browser-description]');
  const browserEmpty = root.querySelector<HTMLElement>('[data-node-browser-empty]');
  const browserTitle = root.querySelector<HTMLElement>('[data-node-browser-title]');
  const openButton = root.querySelector<HTMLButtonElement>('[data-open-node-browser]');
  const searchInput = root.querySelector<HTMLInputElement>('[data-node-browser-search]');
  const searchWrap = root.querySelector<HTMLElement>('[data-node-browser-search-wrap]');

  if (
    !backButton ||
    !browser ||
    !browserContent ||
    !browserDescription ||
    !browserEmpty ||
    !browserTitle ||
    !openButton ||
    !searchInput ||
    !searchWrap
  ) {
    return null;
  }

  return {
    backButton,
    browser,
    browserContent,
    browserDescription,
    browserEmpty,
    browserTitle,
    openButton,
    searchInput,
    searchWrap,
  };
}

export function getCanvasElements(root: ParentNode): CanvasElements | null {
  const board = root.querySelector<HTMLElement>('[data-workflow-board]');
  const definitionInput = root.querySelector<HTMLInputElement | HTMLTextAreaElement>('#id_definition');
  const edgeControls = root.querySelector<HTMLElement>('[data-workflow-edge-controls]');
  const edgeLayer = root.querySelector<SVGSVGElement>('[data-workflow-edge-layer]');
  const emptyState = root.querySelector<HTMLElement>('[data-workflow-empty-state]');
  const fitViewButton = root.querySelector<HTMLButtonElement>('[data-workflow-fit-view]');
  const nodeLayer = root.querySelector<HTMLElement>('[data-workflow-node-layer]');
  const nodeMenu = root.querySelector<HTMLElement>('[data-workflow-node-menu]');
  const settingsDescription = root.querySelector<HTMLElement>('[data-workflow-settings-description]');
  const settingsFields = root.querySelector<HTMLElement>('[data-workflow-settings-fields]');
  const settingsPanel = root.querySelector<HTMLElement>('[data-workflow-settings-panel]');
  const settingsTitle = root.querySelector<HTMLElement>('[data-workflow-settings-title]');
  const surface = root.querySelector<HTMLElement>('[data-workflow-surface]');
  const zoomInButton = root.querySelector<HTMLButtonElement>('[data-workflow-zoom-in]');
  const zoomLabel = root.querySelector<HTMLElement>('[data-workflow-zoom-label]');
  const zoomOutButton = root.querySelector<HTMLButtonElement>('[data-workflow-zoom-out]');

  if (
    !board ||
    !definitionInput ||
    !edgeControls ||
    !edgeLayer ||
    !emptyState ||
    !fitViewButton ||
    !nodeLayer ||
    !nodeMenu ||
    !settingsDescription ||
    !settingsFields ||
    !settingsPanel ||
    !settingsTitle ||
    !surface ||
    !zoomInButton ||
    !zoomLabel ||
    !zoomOutButton
  ) {
    return null;
  }

  return {
    board,
    definitionInput,
    edgeControls,
    edgeLayer,
    emptyState,
    fitViewButton,
    nodeLayer,
    nodeMenu,
    settingsDescription,
    settingsFields,
    settingsPanel,
    settingsTitle,
    surface,
    zoomInButton,
    zoomLabel,
    zoomOutButton,
  };
}

export function getExecutionElements(root: ParentNode): ExecutionElements | null {
  const nodeRunButton = root.querySelector<HTMLButtonElement>('[data-workflow-run-selected-node]');
  const runButton = root.querySelector<HTMLButtonElement>('[data-workflow-run]');
  const error = root.querySelector<HTMLElement>('[data-workflow-execution-error]');
  const result = root.querySelector<HTMLElement>('[data-workflow-execution-result]');
  const resultBadge = root.querySelector<HTMLElement>('[data-workflow-execution-badge]');
  const resultContext = root.querySelector<HTMLElement>('[data-workflow-execution-context]');
  const resultEmpty = root.querySelector<HTMLElement>('[data-workflow-execution-empty]');
  const resultError = root.querySelector<HTMLElement>('[data-workflow-execution-run-error]');
  const resultOutput = root.querySelector<HTMLElement>('[data-workflow-execution-output]');
  const resultSummary = root.querySelector<HTMLElement>('[data-workflow-execution-summary]');
  const resultTitle = root.querySelector<HTMLElement>('[data-workflow-execution-title]');
  const resultTrace = root.querySelector<HTMLElement>('[data-workflow-execution-trace]');
  const status = root.querySelector<HTMLElement>('[data-workflow-execution-status]');

  if (
    !runButton ||
    !error ||
    !result ||
    !resultBadge ||
    !resultContext ||
    !resultEmpty ||
    !resultError ||
    !resultOutput ||
    !resultSummary ||
    !resultTitle ||
    !resultTrace ||
    !status
  ) {
    return null;
  }

  return {
    error,
    nodeRunButton,
    result,
    resultBadge,
    resultContext,
    resultEmpty,
    resultError,
    resultOutput,
    resultSummary,
    resultTitle,
    resultTrace,
    runButton,
    status,
  };
}
