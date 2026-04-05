import type { BrowserElements, CanvasElements } from '../dom';
import type { AgentAuxiliaryPortId, WorkflowNodeTemplateField } from '../types';
import type { ExecutionInspectorTab } from '../state/executionController';

type SettingsFieldInputMetadata = Pick<WorkflowNodeTemplateField, 'type' | 'value_type'>;

async function copyTextToClipboard(value: string): Promise<void> {
  if (!value) {
    return;
  }

  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const fallbackInput = document.createElement('textarea');
  fallbackInput.value = value;
  fallbackInput.setAttribute('readonly', 'true');
  fallbackInput.style.position = 'fixed';
  fallbackInput.style.opacity = '0';
  fallbackInput.style.pointerEvents = 'none';
  document.body.appendChild(fallbackInput);
  fallbackInput.select();
  document.execCommand('copy');
  document.body.removeChild(fallbackInput);
}

export function registerWorkflowDesignerUiBindings(params: {
  addNode: (nodeType: string) => void;
  addSelectedNodeCollectionItem: (fieldKey: string, optionKey: string) => void;
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
  getConnectionDraftActive: () => boolean;
  getContextMenuNodeId: () => string | null;
  getIsBrowserOpen: () => boolean;
  getSelectedNodeId: () => string | null;
  getSettingsNodeId: () => string | null;
  goBackBrowserView: () => void;
  isTextEntryTarget: (target: EventTarget | null) => boolean;
  navigateBrowser: (action: string, appId?: string) => void;
  openAuxiliaryInsertBrowser: (targetId: string, targetPort: AgentAuxiliaryPortId) => void;
  openBrowser: () => void;
  openConnectionPopup: (url: string, options?: { defaultConnectionType?: string }) => void;
  openNodeSettings: (nodeId: string) => void;
  removeEdge: (edgeId: string) => void;
  removeSelectedNodeCollectionItem: (fieldKey: string, optionKey: string, itemIndex: number) => void;
  renderBrowser: () => void;
  repositionGraph: () => void;
  root: HTMLElement;
  runNode: (nodeId: string) => void;
  runSelectedNode: () => void;
  runWorkflow: () => void;
  selectSettingsTab: (tab: 'parameters' | 'settings') => void;
  selectExecutionStep: (stepIndex: number) => void;
  selectExecutionTab: (tab: ExecutionInspectorTab) => void;
  setSearchQuery: (value: string) => void;
  toggleNodeDisabled: (nodeId: string) => void;
  updateSelectedNodeField: (
    key: string,
    value: string,
    options?: { rerenderSettings?: boolean },
  ) => void;
  updateSelectedNodeFieldPath: (
    path: string,
    value: string,
    field: SettingsFieldInputMetadata,
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
    addSelectedNodeCollectionItem,
    applyNodeSettingSuggestion,
    browser,
    canvas,
    cancelConnection,
    closeBrowser,
    closeNodeContextMenu,
    closeNodeSettings,
    deleteNode,
    getConnectionDraftActive,
    getContextMenuNodeId,
    getIsBrowserOpen,
    getSelectedNodeId,
    getSettingsNodeId,
    goBackBrowserView,
    isTextEntryTarget,
    navigateBrowser,
    openAuxiliaryInsertBrowser,
    openBrowser,
    openConnectionPopup,
    openNodeSettings,
    removeEdge,
    removeSelectedNodeCollectionItem,
    renderBrowser,
    repositionGraph,
    root,
    runNode,
    runSelectedNode,
    runWorkflow,
    selectSettingsTab,
    selectExecutionStep,
    selectExecutionTab,
    setSearchQuery,
    toggleNodeDisabled,
    updateSelectedNodeField,
    updateSelectedNodeFieldPath,
    updateSelectedNodeFieldMode,
    updateSelectedNodeLabel,
    zoomByStep,
  } = params;

  root.addEventListener('click', (event) => {
    const target = event.target as HTMLElement;
    const webhookEndpointField = target.closest<HTMLInputElement>('[data-webhook-endpoint-copy="true"]');
    if (webhookEndpointField) {
      webhookEndpointField.select();
      void copyTextToClipboard(webhookEndpointField.value);
      return;
    }

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

    const connectionCreateButton = target.closest<HTMLElement>('[data-workflow-connection-create]');
    if (connectionCreateButton?.dataset.workflowConnectionCreate) {
      openConnectionPopup(connectionCreateButton.dataset.workflowConnectionCreate, {
        defaultConnectionType: connectionCreateButton.dataset.workflowConnectionDefaultType,
      });
      return;
    }

    const connectionEditButton = target.closest<HTMLElement>('[data-workflow-connection-edit]');
    if (connectionEditButton?.dataset.workflowConnectionEdit) {
      openConnectionPopup(connectionEditButton.dataset.workflowConnectionEdit);
      return;
    }

    const connectionOauthButton = target.closest<HTMLElement>('[data-workflow-connection-oauth]');
    if (connectionOauthButton?.dataset.workflowConnectionOauth) {
      openConnectionPopup(connectionOauthButton.dataset.workflowConnectionOauth);
      return;
    }

    if (target.closest('[data-workflow-run-selected-node]')) {
      runSelectedNode();
      return;
    }

    const addCollectionItemButton = target.closest<HTMLElement>('[data-node-setting-collection-add]');
    if (
      addCollectionItemButton?.dataset.nodeSettingCollectionField &&
      addCollectionItemButton.dataset.nodeSettingCollectionOption
    ) {
      addSelectedNodeCollectionItem(
        addCollectionItemButton.dataset.nodeSettingCollectionField,
        addCollectionItemButton.dataset.nodeSettingCollectionOption,
      );
      return;
    }

    const removeCollectionItemButton = target.closest<HTMLElement>('[data-node-setting-collection-remove]');
    if (
      removeCollectionItemButton?.dataset.nodeSettingCollectionField &&
      removeCollectionItemButton.dataset.nodeSettingCollectionOption &&
      removeCollectionItemButton.dataset.nodeSettingCollectionIndex
    ) {
      const itemIndex = Number.parseInt(removeCollectionItemButton.dataset.nodeSettingCollectionIndex, 10);
      if (!Number.isNaN(itemIndex)) {
        removeSelectedNodeCollectionItem(
          removeCollectionItemButton.dataset.nodeSettingCollectionField,
          removeCollectionItemButton.dataset.nodeSettingCollectionOption,
          itemIndex,
        );
      }
      return;
    }

    if (target.closest('[data-workflow-run-previous-nodes]')) {
      runSelectedNode();
      return;
    }

    const settingsTab = target.closest<HTMLElement>('[data-workflow-settings-tab]');
    if (
      settingsTab?.dataset.workflowSettingsTab === 'parameters'
      || settingsTab?.dataset.workflowSettingsTab === 'settings'
    ) {
      selectSettingsTab(settingsTab.dataset.workflowSettingsTab);
      return;
    }

    const executionTab = target.closest<HTMLElement>('[data-workflow-execution-tab]');
    if (executionTab?.dataset.workflowExecutionTab) {
      const tab = executionTab.dataset.workflowExecutionTab;
      if (
        tab === 'overview' ||
        tab === 'output' ||
        tab === 'input' ||
        tab === 'context' ||
        tab === 'steps' ||
        tab === 'trace'
      ) {
        selectExecutionTab(tab);
      }
      return;
    }

    const executionStep = target.closest<HTMLElement>('[data-workflow-execution-step-index]');
    if (executionStep?.dataset.workflowExecutionStepIndex) {
      const stepIndex = Number.parseInt(executionStep.dataset.workflowExecutionStepIndex, 10);
      if (!Number.isNaN(stepIndex)) {
        selectExecutionStep(stepIndex);
      }
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
        runNode(nodeId);
        return;
      }
      if (action === 'toggle-disabled') {
        toggleNodeDisabled(nodeId);
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
      navigateBrowser(browserNavigation.dataset.nodeBrowserNav, browserNavigation.dataset.appId);
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

    const path = target.dataset.nodeSettingPath;
    if (path) {
      const type = target.dataset.nodeSettingType;
      if (
        type === 'text' ||
        type === 'datetime' ||
        type === 'textarea' ||
        type === 'select' ||
        type === 'node_target' ||
        type === 'fixed_collection'
      ) {
        updateSelectedNodeFieldPath(path, target.value, {
          type,
          value_type: target.dataset.nodeSettingValueType,
        });
      }
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

    const path = target.dataset.nodeSettingPath;
    if (path) {
      const type = target.dataset.nodeSettingType;
      if (
        type === 'text' ||
        type === 'datetime' ||
        type === 'textarea' ||
        type === 'select' ||
        type === 'node_target' ||
        type === 'fixed_collection'
      ) {
        updateSelectedNodeFieldPath(path, target.value, {
          type,
          value_type: target.dataset.nodeSettingValueType,
        }, { rerenderSettings: true });
      }
      return;
    }

    const key = target.dataset.nodeSettingKey;
    if (!key) {
      return;
    }

    updateSelectedNodeField(key, target.value, { rerenderSettings: true });
  });
}
