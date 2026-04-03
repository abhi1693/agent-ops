import type { BrowserElements, CanvasElements } from '../dom';
import type { BrowserView } from '../panels/browserState';
import type { AgentAuxiliaryPortId } from '../types';

export function registerWorkflowDesignerUiBindings(params: {
  addNode: (nodeType: string) => void;
  applyNodeSettingSuggestion: (
    key: string,
    value: string,
    binding: 'literal' | 'path' | 'template',
  ) => void;
  browser: BrowserElements;
  canvas: CanvasElements;
  cancelConnection: () => void;
  closeBrowser: () => void;
  closeNodeContextMenu: () => void;
  closeNodeSettings: () => void;
  deleteNode: (nodeId: string) => void;
  getBrowserView: () => BrowserView;
  getConnectionDraftActive: () => boolean;
  getContextMenuNodeId: () => string | null;
  getIsBrowserOpen: () => boolean;
  getSelectedNodeId: () => string | null;
  getSettingsNodeId: () => string | null;
  goBackBrowserView: () => void;
  isEmptyWorkflow: () => boolean;
  isTextEntryTarget: (target: EventTarget | null) => boolean;
  openAuxiliaryInsertBrowser: (targetId: string, targetPort: AgentAuxiliaryPortId) => void;
  openBrowser: () => void;
  openNodeSettings: (nodeId: string) => void;
  removeEdge: (edgeId: string) => void;
  renderBrowser: () => void;
  repositionGraph: () => void;
  root: HTMLElement;
  runNode: (nodeId: string) => void;
  runSelectedNode: () => void;
  runWorkflow: () => void;
  setBrowserView: (nextView: BrowserView) => void;
  setSearchQuery: (value: string) => void;
  updateSelectedNodeField: (
    key: string,
    value: string,
    options?: { rerenderSettings?: boolean },
  ) => void;
  updateSelectedNodeFieldMode: (
    key: string,
    mode: 'expression' | 'static',
    options?: { rerenderSettings?: boolean },
  ) => void;
  updateSelectedNodeLabel: (value: string, options?: { rerenderSettings?: boolean }) => void;
  zoomByStep: (direction: 'in' | 'out') => void;
}): void {
  const {
    addNode,
    applyNodeSettingSuggestion,
    browser,
    canvas,
    cancelConnection,
    closeBrowser,
    closeNodeContextMenu,
    closeNodeSettings,
    deleteNode,
    getBrowserView,
    getConnectionDraftActive,
    getContextMenuNodeId,
    getIsBrowserOpen,
    getSelectedNodeId,
    getSettingsNodeId,
    goBackBrowserView,
    isEmptyWorkflow,
    isTextEntryTarget,
    openAuxiliaryInsertBrowser,
    openBrowser,
    openNodeSettings,
    removeEdge,
    renderBrowser,
    repositionGraph,
    root,
    runNode,
    runSelectedNode,
    runWorkflow,
    setBrowserView,
    setSearchQuery,
    updateSelectedNodeField,
    updateSelectedNodeFieldMode,
    updateSelectedNodeLabel,
    zoomByStep,
  } = params;

  root.addEventListener('click', (event) => {
    const target = event.target as HTMLElement;

    const settingModeButton = target.closest<HTMLElement>('[data-node-setting-mode-key]');
    if (
      settingModeButton?.dataset.nodeSettingModeKey &&
      (settingModeButton.dataset.nodeSettingMode === 'static' || settingModeButton.dataset.nodeSettingMode === 'expression')
    ) {
      updateSelectedNodeFieldMode(
        settingModeButton.dataset.nodeSettingModeKey,
        settingModeButton.dataset.nodeSettingMode,
        { rerenderSettings: true },
      );
      return;
    }

    const settingChip = target.closest<HTMLElement>('[data-node-setting-chip-key]');
    if (
      settingChip?.dataset.nodeSettingChipKey &&
      settingChip.dataset.nodeSettingChipValue &&
      (settingChip.dataset.nodeSettingChipBinding === 'literal' ||
        settingChip.dataset.nodeSettingChipBinding === 'path' ||
        settingChip.dataset.nodeSettingChipBinding === 'template')
    ) {
      applyNodeSettingSuggestion(
        settingChip.dataset.nodeSettingChipKey,
        settingChip.dataset.nodeSettingChipValue,
        settingChip.dataset.nodeSettingChipBinding,
      );
      return;
    }

    if (target.closest('[data-workflow-run]')) {
      runWorkflow();
      return;
    }

    if (target.closest('[data-workflow-run-selected-node]')) {
      runSelectedNode();
      return;
    }

    if (target.closest('[data-workflow-fit-view]')) {
      repositionGraph();
      return;
    }

    if (target.closest('[data-workflow-zoom-in]')) {
      zoomByStep('in');
      return;
    }

    if (target.closest('[data-workflow-zoom-out]')) {
      zoomByStep('out');
      return;
    }

    const nodeAction = target.closest<HTMLElement>('[data-node-action]');
    if (nodeAction?.dataset.nodeAction && nodeAction.dataset.nodeActionId) {
      const nodeId = nodeAction.dataset.nodeActionId;
      const action = nodeAction.dataset.nodeAction;

      if (action === 'run') {
        openNodeSettings(nodeId);
        runNode(nodeId);
        return;
      }
      if (action === 'settings') {
        openNodeSettings(nodeId);
        return;
      }
      if (action === 'delete') {
        deleteNode(nodeId);
        return;
      }
    }

    if (target.closest('[data-open-node-browser]')) {
      if (getIsBrowserOpen()) {
        closeBrowser();
      } else {
        openBrowser();
      }
      return;
    }

    if (target.closest('[data-open-empty-browser]')) {
      openBrowser();
      return;
    }

    if (target.closest('[data-close-node-browser]')) {
      closeBrowser();
      return;
    }

    if (target.closest('[data-node-browser-back]')) {
      goBackBrowserView();
      return;
    }

    if (getContextMenuNodeId() && !target.closest('[data-workflow-node-menu]')) {
      closeNodeContextMenu();
    }

    if (target.closest('[data-close-node-settings]')) {
      closeNodeSettings();
      return;
    }

    const removeEdgeButton = target.closest<HTMLElement>('[data-remove-edge]');
    if (removeEdgeButton?.dataset.removeEdge) {
      removeEdge(removeEdgeButton.dataset.removeEdge);
      return;
    }

    const nodeMenuAction = target.closest<HTMLElement>('[data-node-menu-action]');
    const contextMenuNodeId = getContextMenuNodeId();
    if (nodeMenuAction?.dataset.nodeMenuAction && contextMenuNodeId) {
      const action = nodeMenuAction.dataset.nodeMenuAction;
      closeNodeContextMenu();
      if (action === 'settings') {
        openNodeSettings(contextMenuNodeId);
        return;
      }
      if (action === 'delete') {
        deleteNode(contextMenuNodeId);
        return;
      }
    }

    const browserItem = target.closest<HTMLElement>('[data-node-browser-item]');
    if (browserItem?.dataset.nodeBrowserItem) {
      addNode(browserItem.dataset.nodeBrowserItem);
      return;
    }

    const browserNavigation = target.closest<HTMLElement>('[data-node-browser-nav]');
    if (browserNavigation?.dataset.nodeBrowserNav) {
      const browserView = getBrowserView();

      if (browserNavigation.dataset.nodeBrowserNav === 'trigger-apps') {
        setBrowserView({
          backTo: browserView.kind === 'trigger-root' && browserView.backTo === 'next-step-root'
            ? 'next-step-root'
            : 'trigger-root',
          kind: 'trigger-apps',
        });
        renderBrowser();
        return;
      }

      if (browserNavigation.dataset.nodeBrowserNav === 'app-details' && browserNavigation.dataset.appId) {
        setBrowserView({
          appId: browserNavigation.dataset.appId,
          backTo: browserView.kind === 'trigger-apps' ? 'trigger-apps' : 'app-actions',
          kind: 'app-details',
        });
        renderBrowser();
        return;
      }

      if (browserNavigation.dataset.nodeBrowserNav === 'app-actions') {
        setBrowserView({ kind: 'app-actions' });
        renderBrowser();
        return;
      }

      if (browserNavigation.dataset.nodeBrowserNav === 'trigger-root') {
        setBrowserView(isEmptyWorkflow() ? { kind: 'trigger-root' } : { backTo: 'next-step-root', kind: 'trigger-root' });
        renderBrowser();
        return;
      }

      if (browserNavigation.dataset.nodeBrowserNav === 'next-ai') {
        setBrowserView({ category: 'ai', kind: 'category-details' });
        renderBrowser();
        return;
      }

      if (browserNavigation.dataset.nodeBrowserNav === 'next-data') {
        setBrowserView({ category: 'data', kind: 'category-details' });
        renderBrowser();
        return;
      }

      if (browserNavigation.dataset.nodeBrowserNav === 'next-flow') {
        setBrowserView({ category: 'flow', kind: 'category-details' });
        renderBrowser();
        return;
      }

      if (browserNavigation.dataset.nodeBrowserNav === 'next-core') {
        setBrowserView({ category: 'core', kind: 'category-details' });
        renderBrowser();
        return;
      }
      return;
    }

    const auxiliaryPort = target.closest<HTMLElement>('[data-workflow-node-aux-port]');
    const auxiliaryTargetId = auxiliaryPort?.dataset.workflowNodeAuxNode;
    const auxiliaryTargetPort = auxiliaryPort?.dataset.workflowNodeAuxPort as AgentAuxiliaryPortId | undefined;
    if (auxiliaryTargetId && auxiliaryTargetPort) {
      openAuxiliaryInsertBrowser(auxiliaryTargetId, auxiliaryTargetPort);
    }
  });

  root.addEventListener('keydown', (event) => {
    if (
      (event.key === 'Delete' || event.key === 'Backspace') &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.altKey &&
      getSelectedNodeId() &&
      !isTextEntryTarget(event.target)
    ) {
      deleteNode(getSelectedNodeId() as string);
      event.preventDefault();
      return;
    }

    if (event.key !== 'Escape') {
      const target = event.target as HTMLElement | null;
      const auxiliaryPort = target?.closest<HTMLElement>('[data-workflow-node-aux-port]');
      const auxiliaryTargetId = auxiliaryPort?.dataset.workflowNodeAuxNode;
      const auxiliaryTargetPort = auxiliaryPort?.dataset.workflowNodeAuxPort as AgentAuxiliaryPortId | undefined;
      if (
        auxiliaryTargetId &&
        auxiliaryTargetPort &&
        (event.key === 'Enter' || event.key === ' ')
      ) {
        openAuxiliaryInsertBrowser(auxiliaryTargetId, auxiliaryTargetPort);
        event.preventDefault();
      }
      return;
    }

    if (getConnectionDraftActive()) {
      cancelConnection();
      return;
    }

    if (getIsBrowserOpen()) {
      closeBrowser();
      return;
    }

    if (getContextMenuNodeId()) {
      closeNodeContextMenu();
      return;
    }

    if (getSettingsNodeId()) {
      closeNodeSettings();
    }
  });

  browser.searchInput.addEventListener('input', () => {
    setSearchQuery(browser.searchInput.value);
    renderBrowser();
  });

  canvas.settingsFields.addEventListener('input', (event) => {
    const target = event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
    if (target.matches('[data-node-setting-label]')) {
      updateSelectedNodeLabel(target.value);
      return;
    }

    const key = target.dataset.nodeSettingKey;
    if (!key) {
      return;
    }

    updateSelectedNodeField(key, target.value);
  });

  canvas.settingsFields.addEventListener('change', (event) => {
    const target = event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
    if (target.matches('[data-node-setting-label]')) {
      updateSelectedNodeLabel(target.value, { rerenderSettings: true });
      return;
    }

    const key = target.dataset.nodeSettingKey;
    if (!key) {
      return;
    }

    updateSelectedNodeField(key, target.value, { rerenderSettings: true });
  });
}
