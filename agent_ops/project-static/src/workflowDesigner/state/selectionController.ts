import type { WorkflowNode } from '../types';

export type WorkflowNodeContextMenuState = {
  nodeId: string;
  x: number;
  y: number;
};

export function createWorkflowDesignerSelectionController(params: {
  getContextMenuPosition: (clientX: number, clientY: number) => { x: number; y: number };
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  renderCanvas: () => void;
  renderNodeContextMenu: () => void;
  renderSettingsPanel: () => void;
}): {
  cleanupDeletedNode: (nodeId: string) => void;
  clearContextMenuState: () => void;
  closeNodeContextMenu: () => void;
  closeNodeSettings: () => void;
  getContextMenuState: () => WorkflowNodeContextMenuState | null;
  getSelectedNodeId: () => string | null;
  getSettingsNodeId: () => string | null;
  hasOpenContextMenu: () => boolean;
  openNodeContextMenu: (nodeId: string, clientX: number, clientY: number) => void;
  openNodeSettings: (nodeId: string) => void;
  setSelectedNodeId: (nodeId: string | null) => void;
  setSettingsNodeId: (nodeId: string | null) => void;
} {
  const {
    getContextMenuPosition,
    getNode,
    renderCanvas,
    renderNodeContextMenu,
    renderSettingsPanel,
  } = params;

  let selectedNodeId: string | null = null;
  let settingsNodeId: string | null = null;
  let contextMenuState: WorkflowNodeContextMenuState | null = null;

  function openNodeSettings(nodeId: string): void {
    selectedNodeId = nodeId;
    settingsNodeId = nodeId;
    contextMenuState = null;
    renderCanvas();
    renderSettingsPanel();
  }

  function closeNodeSettings(): void {
    settingsNodeId = null;
    renderSettingsPanel();
  }

  function closeNodeContextMenu(): void {
    contextMenuState = null;
    renderNodeContextMenu();
  }

  function openNodeContextMenu(nodeId: string, clientX: number, clientY: number): void {
    const node = getNode(nodeId);
    if (!node) {
      return;
    }

    selectedNodeId = nodeId;
    settingsNodeId = null;
    contextMenuState = {
      nodeId,
      ...getContextMenuPosition(clientX, clientY),
    };
    renderCanvas();
    renderSettingsPanel();
  }

  function cleanupDeletedNode(nodeId: string): void {
    if (selectedNodeId === nodeId) {
      selectedNodeId = null;
    }
    if (settingsNodeId === nodeId) {
      settingsNodeId = null;
    }
    if (contextMenuState?.nodeId === nodeId) {
      contextMenuState = null;
    }
  }

  return {
    cleanupDeletedNode,
    clearContextMenuState: () => {
      contextMenuState = null;
    },
    closeNodeContextMenu,
    closeNodeSettings,
    getContextMenuState: () => contextMenuState,
    getSelectedNodeId: () => selectedNodeId,
    getSettingsNodeId: () => settingsNodeId,
    hasOpenContextMenu: () => Boolean(contextMenuState),
    openNodeContextMenu,
    openNodeSettings,
    setSelectedNodeId: (nodeId) => {
      selectedNodeId = nodeId;
    },
    setSettingsNodeId: (nodeId) => {
      settingsNodeId = nodeId;
    },
  };
}
