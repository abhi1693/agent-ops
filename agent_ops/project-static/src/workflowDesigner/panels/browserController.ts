import {
  NODE_HEIGHT,
  NODE_WIDTH,
} from '../constants';
import type { BrowserElements } from '../dom';
import { clampNodePosition, getAgentAuxiliaryPortPoint, getNodeRenderHeight } from '../geometry';
import {
  getAgentAuxiliaryAllowedNodeTypes,
  getAgentAuxiliaryPortDefinition,
} from '../interactions/connections';
import type {
  AgentAuxiliaryPortId,
  Point,
  WorkflowCatalogGroup,
  WorkflowCatalogSection,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeSelectionPresentation,
  WorkflowPaletteSection,
} from '../types';
import {
  BrowserView,
  getDefaultBrowserView,
  getPreviousBrowserView,
  renderBrowserState,
} from './browserState';

export type WorkflowBrowserInsertDraft = {
  allowedNodeTypes?: string[];
  position: {
    x: number;
    y: number;
  };
  sourceId?: string;
  targetId?: string;
  targetPort?: AgentAuxiliaryPortId;
};

export function createWorkflowDesignerBrowserController(params: {
  board: HTMLElement;
  browser: BrowserElements;
  groups: WorkflowCatalogGroup[];
  presentation: WorkflowNodeSelectionPresentation;
  clearContextMenuState: () => void;
  clearSettingsNodeId: () => void;
  catalogSections: WorkflowCatalogSection[];
  definitions: WorkflowNodeDefinition[];
  getAvailableSections: () => WorkflowPaletteSection[];
  getIsEmptyWorkflow: () => boolean;
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getWorkflowDefinition: () => WorkflowDefinition;
  initialIsOpen: boolean;
  initialView: BrowserView;
  openNodeSettings: (nodeId: string) => void;
  renderCanvas: () => void;
  renderNodeContextMenu: () => void;
  renderSettingsPanel: () => void;
  screenToWorld: (clientX: number, clientY: number) => Point;
  setSelectedNodeId: (nodeId: string) => void;
}): {
  closeBrowser: () => void;
  getInsertDraft: () => WorkflowBrowserInsertDraft | null;
  getIsBrowserOpen: () => boolean;
  goBackBrowserView: () => void;
  navigateBrowser: (action: string, appId?: string) => void;
  openAuxiliaryInsertBrowser: (targetId: string, targetPort: AgentAuxiliaryPortId) => void;
  openBrowser: () => void;
  openInsertBrowser: (sourceId: string, clientX: number, clientY: number) => void;
  renderBrowser: () => void;
  setSearchQuery: (value: string) => void;
  showEmptyWorkflowBrowser: () => void;
} {
  const {
    board,
    browser,
    groups,
    presentation,
    clearContextMenuState,
    clearSettingsNodeId,
    catalogSections,
    definitions,
    getAvailableSections,
    getIsEmptyWorkflow,
    getNode,
    getWorkflowDefinition,
    initialIsOpen,
    initialView,
    openNodeSettings,
    renderCanvas,
    renderNodeContextMenu,
    renderSettingsPanel,
    screenToWorld,
    setSelectedNodeId,
  } = params;

  let isBrowserOpen = initialIsOpen;
  let browserView = initialView;
  let searchQuery = '';
  let insertDraft: WorkflowBrowserInsertDraft | null = null;

  function resetSearch(): void {
    searchQuery = '';
    browser.searchInput.value = '';
  }

  function setBrowserView(nextView: BrowserView): void {
    browserView = nextView;
    resetSearch();
  }

  function renderBrowser(): void {
    const insertPort = getAgentAuxiliaryPortDefinition(insertDraft?.targetPort);
    const allowedNodeTypes = insertDraft?.allowedNodeTypes ?? null;
    const filteredSections = getAvailableSections()
      .map((section) => ({
        ...section,
        definitions: allowedNodeTypes
          ? section.definitions.filter((definition) => allowedNodeTypes.includes(definition.type))
          : section.definitions,
      }))
      .filter((section) => section.definitions.length > 0);
    const browserState = renderBrowserState({
      allowedNodeTypes,
      browserView,
      groups,
      catalogSections,
      definitions,
      filteredSections,
      insertPort: insertPort?.id,
      isEmptyWorkflow: getIsEmptyWorkflow(),
      presentation,
      searchQuery,
    });

    browser.browser.hidden = !isBrowserOpen;
    browser.browser.classList.toggle('is-starter-mode', getIsEmptyWorkflow());
    browser.browserTitle.textContent = browserState.title;
    browser.browserDescription.textContent = browserState.description;
    browser.browserDescription.hidden = browserState.description.length === 0;
    browser.backButton.hidden = !browserState.showBackButton;
    browser.openButton.classList.toggle('is-active', isBrowserOpen);
    browser.searchWrap.hidden = browserState.hideSearch;
    browser.searchInput.placeholder = browserState.searchPlaceholder;
    browser.browserContent.innerHTML = browserState.markup;
    browser.browserEmpty.textContent = browserState.emptyMessage;
    browser.browserEmpty.hidden = browserState.markup.length > 0;
  }

  function goBackBrowserView(): void {
    const previousView = getPreviousBrowserView(browserView, getIsEmptyWorkflow());
    if (previousView) {
      setBrowserView(previousView);
      renderBrowser();
    }
  }

  function navigateBrowser(action: string, appId?: string): void {
    if (action === 'trigger-apps') {
      setBrowserView({
        backTo: browserView.kind === 'trigger-root' && browserView.backTo === 'next-step-root'
          ? 'next-step-root'
          : 'trigger-root',
        kind: 'trigger-apps',
      });
      renderBrowser();
      return;
    }

    if (action === 'app-details' && appId) {
      setBrowserView({
        appId,
        backTo: browserView.kind === 'trigger-apps' ? 'trigger-apps' : 'app-actions',
        kind: 'app-details',
      });
      renderBrowser();
      return;
    }

    if (action === 'app-actions') {
      setBrowserView({ kind: 'app-actions' });
      renderBrowser();
      return;
    }

    if (action === 'trigger-root') {
      setBrowserView(getIsEmptyWorkflow() ? { kind: 'trigger-root' } : { backTo: 'next-step-root', kind: 'trigger-root' });
      renderBrowser();
      return;
    }

    if (action.startsWith('next-category:')) {
      const categoryId = action.slice('next-category:'.length).trim();
      if (!categoryId) {
        return;
      }

      setBrowserView({ category: categoryId, kind: 'category-details' });
      renderBrowser();
      return;
    }
  }

  function closeBrowser(): void {
    isBrowserOpen = false;
    insertDraft = null;
    clearContextMenuState();
    browserView = getDefaultBrowserView(getIsEmptyWorkflow());
    resetSearch();
    renderBrowser();
    renderNodeContextMenu();
  }

  function openBrowser(): void {
    isBrowserOpen = true;
    clearContextMenuState();
    setBrowserView(getDefaultBrowserView(getIsEmptyWorkflow()));
    renderBrowser();
    renderNodeContextMenu();
    window.setTimeout(() => {
      browser.searchInput.focus();
    }, 0);
  }

  function openInsertBrowser(sourceId: string, clientX: number, clientY: number): void {
    const worldPoint = screenToWorld(clientX, clientY);
    insertDraft = {
      position: clampNodePosition(board, {
        x: worldPoint.x - NODE_WIDTH / 2,
        y: worldPoint.y - NODE_HEIGHT / 2,
      }, NODE_HEIGHT),
      sourceId,
    };
    openBrowser();
  }

  function openAuxiliaryInsertBrowser(targetId: string, targetPort: AgentAuxiliaryPortId): void {
    const workflowDefinition = getWorkflowDefinition();
    const targetNode = getNode(targetId);
    const portDefinition = getAgentAuxiliaryPortDefinition(targetPort);
    if (!targetNode || !portDefinition) {
      return;
    }

    const existingModelEdge = targetPort === 'ai_languageModel'
      ? workflowDefinition.edges.find((edge) => edge.target === targetId && edge.targetPort === targetPort)
      : undefined;
    if (existingModelEdge) {
      openNodeSettings(existingModelEdge.source);
      return;
    }

    const portPoint = getAgentAuxiliaryPortPoint(targetNode, targetPort);
    const targetNodeHeight = getNodeRenderHeight(targetNode);
    insertDraft = {
      allowedNodeTypes: getAgentAuxiliaryAllowedNodeTypes(definitions, targetPort),
      position: clampNodePosition(board, {
        x: portPoint.x - NODE_WIDTH / 2,
        y: targetNode.position.y + targetNodeHeight + 44,
      }, NODE_HEIGHT),
      targetId,
      targetPort,
    };
    setSelectedNodeId(targetId);
    clearSettingsNodeId();
    openBrowser();
    renderCanvas();
    renderSettingsPanel();
  }

  function setSearchQuery(value: string): void {
    searchQuery = value;
  }

  function showEmptyWorkflowBrowser(): void {
    isBrowserOpen = true;
    resetSearch();
  }

  return {
    closeBrowser,
    getInsertDraft: () => insertDraft,
    getIsBrowserOpen: () => isBrowserOpen,
    goBackBrowserView,
    navigateBrowser,
    openAuxiliaryInsertBrowser,
    openBrowser,
    openInsertBrowser,
    renderBrowser,
    setSearchQuery,
    showEmptyWorkflowBrowser,
  };
}
