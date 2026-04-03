import {
  NODE_HEIGHT,
  NODE_WIDTH,
} from './workflowDesigner/constants';
import {
  getBrowserElements,
  getCanvasElements,
  getExecutionElements,
} from './workflowDesigner/dom';
import {
  renderEdgeRemoveButtonMarkup,
  renderWorkflowEditorEdgesMarkup,
  renderNodeContextMenuMarkup,
  renderWorkflowEditorNodeMarkup,
} from './workflowDesigner/markup';
import {
  clampNodePosition,
  getConnectorPoint,
  getGraphBounds,
  getNodeCenter,
  getNodeRenderHeight,
  getNodeRenderWidth,
  getPreferredConnectorSide,
  getSuggestedNodePosition,
} from './workflowDesigner/geometry';
import {
  AGENT_AUXILIARY_PORTS,
  canNodeEmitConnections,
  canNodeReceiveConnections,
  getCompatibleAgentAuxiliaryPort,
  getHoveredTarget as getHoveredConnectionTarget,
  isValidConnection as validateConnection,
} from './workflowDesigner/interactions/connections';
import {
  registerWorkflowDesignerPointerInteractions,
  type ConnectionDraft,
  type DragState,
  type PanState,
} from './workflowDesigner/interactions/pointerController';
import { registerWorkflowDesignerUiBindings } from './workflowDesigner/interactions/uiBindings';
import {
  getDefaultBrowserView,
} from './workflowDesigner/panels/browserState';
import { createWorkflowDesignerBrowserController } from './workflowDesigner/panels/browserController';
import {
  renderSettingsIdentitySection,
  renderNodeSettingsFieldsMarkup,
  renderSettingsOverviewSection,
} from './workflowDesigner/panels/settingsPanel';
import { createWorkflowDesignerSettingsController } from './workflowDesigner/panels/settingsController';
import {
  getAvailableInputPaths,
} from './workflowDesigner/panels/settingsAssist';
import {
  buildWorkflowEditorNodePresentation,
  getFieldOptionsWithCurrentValue,
} from './workflowDesigner/presenters/nodePresentation';
import { buildWorkflowEditorEdgesPresentation } from './workflowDesigner/presenters/edgePresentation';
import { buildNodeRegistry, getAvailablePaletteSections } from './workflowDesigner/registry/nodeRegistry';
import { normalizeWorkflowDefinition, serializeWorkflowDefinition } from './workflowDesigner/schema/workflowSchema';
import { createWorkflowDesignerGraphController } from './workflowDesigner/state/graphController';
import { createGraphStore } from './workflowDesigner/state/graphStore';
import { createWorkflowDesignerExecutionController } from './workflowDesigner/state/executionController';
import { createWorkflowDesignerSelectionController } from './workflowDesigner/state/selectionController';
import type {
  AgentAuxiliaryPortId,
  ConnectorSide,
  Point,
  WorkflowCatalogPayload,
  WorkflowConnection,
  WorkflowDefinition,
  WorkflowNodeKind,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeTemplateField,
  WorkflowNodeTemplateOption,
  WorkflowPaletteSection,
  WorkflowPersistedDefinition,
} from './workflowDesigner/types';
import {
  clamp,
  cloneValue,
  createId,
  escapeHtml,
  formatKindLabel,
  getConfigString,
  inferTemplateFieldInputMode,
  getTemplateFieldOptions,
  getTemplateFieldValue,
  isTemplateFieldVisible,
  parseJsonScript,
} from './workflowDesigner/utils';
import { createViewportController } from './workflowDesigner/viewport/controller';

const CONNECTOR_SIDES: ConnectorSide[] = ['top', 'right', 'bottom', 'left'];
const NODE_CONTEXT_MENU_WIDTH = 224;
const NODE_CONTEXT_MENU_HEIGHT = 142;
const NODE_CONTEXT_MENU_MARGIN = 12;
const NODE_CONTEXT_MENU_OFFSET_X = 10;
const NODE_CONTEXT_MENU_OFFSET_Y = 6;
const TERMINAL_RUN_STATUSES = new Set(['succeeded', 'failed']);

function isTerminalRunStatus(status: string): boolean {
  return TERMINAL_RUN_STATUSES.has(status);
}

function parsePersistedDefinition(
  definitionInput: HTMLInputElement | HTMLTextAreaElement,
): WorkflowPersistedDefinition | null {
  if (!definitionInput.value.trim()) {
    return null;
  }

  try {
    return JSON.parse(definitionInput.value) as WorkflowPersistedDefinition;
  } catch (error) {
    console.error(error);
    return null;
  }
}

function getRealAppId(definition: WorkflowNodeDefinition | undefined): string {
  const appId = definition?.app_id?.trim();
  if (!appId || appId === 'builtins') {
    return '';
  }

  return appId;
}

function getRealAppLabel(definition: WorkflowNodeDefinition | undefined): string {
  if (!definition) {
    return '';
  }

  return getRealAppId(definition) ? definition.app_label?.trim() ?? '' : '';
}

function createWorkflowNode(
  board: HTMLElement,
  definition: WorkflowDefinition,
  nodeDefinition: WorkflowNodeDefinition,
  selectedNodeId: string | null,
  overridePosition?: { x: number; y: number },
): WorkflowNode {
  return {
    config: cloneValue(nodeDefinition.config ?? {}),
    id: createId('node'),
    kind: nodeDefinition.kind,
    label: nodeDefinition.label,
    position: clampNodePosition(
      board,
      overridePosition ?? getSuggestedNodePosition(board, definition, selectedNodeId, nodeDefinition),
      getNodeRenderHeight(nodeDefinition),
      getNodeRenderWidth(nodeDefinition),
    ),
    type: nodeDefinition.type,
    typeVersion: nodeDefinition.typeVersion,
  };
}

function getNodeElement(nodeLayer: HTMLElement, nodeId: string): HTMLElement | null {
  return (
    Array.from(nodeLayer.querySelectorAll<HTMLElement>('[data-workflow-node-id]')).find(
      (element) => element.dataset.workflowNodeId === nodeId,
    ) ?? null
  );
}

function setNodeElementPosition(nodeElement: HTMLElement, node: WorkflowNode): void {
  nodeElement.style.left = `${node.position.x}px`;
  nodeElement.style.top = `${node.position.y}px`;
}

function getNodeTargetOptions(currentNode: WorkflowNode, definition: WorkflowDefinition): Array<{ label: string; value: string }> {
  return definition.nodes
    .filter((node) => node.id !== currentNode.id)
    .map((node) => ({
      label: node.label || formatKindLabel(node.kind) || node.type,
      value: node.id,
    }));
}

export function initWorkflowDesigner(): void {
  const root = document.querySelector<HTMLElement>('[data-workflow-designer]');
  if (!root) {
    return;
  }

  const browserElements = getBrowserElements(root);
  const canvasElements = getCanvasElements(root);
  if (!browserElements || !canvasElements) {
    return;
  }
  const browser = browserElements;
  const canvas = canvasElements;
  const execution = getExecutionElements(root);
  const workflowRunUrl = root.dataset.workflowRunUrl ?? '';
  const workflowNodeRunUrlTemplate = root.dataset.workflowNodeRunUrlTemplate ?? '';
  const csrfToken = root.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]')?.value ?? '';

  const fallbackDefinition = parseJsonScript<WorkflowPersistedDefinition>('workflow-definition-data', {
    edges: [],
    nodes: [],
  });
  const persistedDefinition = parsePersistedDefinition(canvas.definitionInput) ?? fallbackDefinition;
  const graphStore = createGraphStore({
    definition: normalizeWorkflowDefinition(persistedDefinition),
    persist(definition) {
      canvas.definitionInput.value = JSON.stringify(serializeWorkflowDefinition(definition));
    },
  });
  const workflowDefinition = graphStore.definition;
  const workflowCatalog = parseJsonScript<WorkflowCatalogPayload>('workflow-catalog-data', {
    definitions: [],
  });
  const workflowConnections = parseJsonScript<WorkflowConnection[]>('workflow-connections-data', []);
  const nodeRegistry = buildNodeRegistry(workflowCatalog.definitions, workflowConnections);
  const viewportController = createViewportController({
    board: canvas.board,
    surface: canvas.surface,
    viewport: {
      x: workflowDefinition.viewport?.x ?? 0,
      y: workflowDefinition.viewport?.y ?? 0,
      zoom: workflowDefinition.viewport?.zoom ?? 1,
    },
    onChange(viewport) {
      graphStore.setViewport(viewport);
      graphStore.commit();
      renderEdges();
      renderNodeContextMenu();
      renderCanvasHud();
    },
  });

  let dragState: DragState | null = null;
  let panState: PanState | null = null;
  let connectionDraft: ConnectionDraft | null = null;
  let hoveredEdgeId: string | null = null;

  function syncDefinitionInput(): void {
    graphStore.commit();
  }

  function getNode(nodeId: string | null): WorkflowNode | undefined {
    return graphStore.getNode(nodeId);
  }

  function getInitialExecutionNodeId(nodeId: string | null): string | null {
    if (nodeId) {
      return nodeId;
    }

    const triggerNode = workflowDefinition.nodes.find((node) => node.kind === 'trigger');
    if (triggerNode) {
      return triggerNode.id;
    }

    return workflowDefinition.nodes[0]?.id ?? null;
  }

  function buildExecutionRequestBody(inputData: Record<string, unknown>): string {
    return JSON.stringify({
      definition: serializeWorkflowDefinition(workflowDefinition),
      input_data: inputData,
    });
  }

  function getNodeRunUrl(nodeId: string): string {
    return workflowNodeRunUrlTemplate.replace('__node_id__', encodeURIComponent(nodeId));
  }

  function isEmptyWorkflow(): boolean {
    return workflowDefinition.nodes.length === 0;
  }

  function isValidConnection(
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ): boolean {
    return validateConnection({
      getNode,
      getNodeDefinition,
      sourceId,
      targetId,
      targetPort,
      workflowDefinition,
    });
  }

  function getPointFromClient(clientX: number, clientY: number): Point {
    return viewportController.screenToWorld(clientX, clientY);
  }

  function getHoveredTarget(
    clientX: number,
    clientY: number,
    sourceId: string,
  ): { nodeId: string; side: ConnectorSide; targetPort: AgentAuxiliaryPortId | null } | null {
    return getHoveredConnectionTarget({
      clientX,
      clientY,
      getElementFromPoint: (nextClientX: number, nextClientY: number) =>
        document.elementFromPoint(nextClientX, nextClientY) as HTMLElement | null,
      getNode,
      getPointFromClient,
      isValidConnection,
      sourceId,
    });
  }

  function getNodeDefinition(node: WorkflowNode | undefined): WorkflowNodeDefinition | undefined {
    if (!node) {
      return undefined;
    }

    return nodeRegistry.definitionMap.get(node.type);
  }

  function getVisibleTargetFields(
    node: WorkflowNode,
    nodeDefinition: WorkflowNodeDefinition | undefined,
  ): WorkflowNodeTemplateField[] {
    if (!nodeDefinition) {
      return [];
    }

    return nodeDefinition.fields.filter(
      (field) => field.type === 'node_target' && isTemplateFieldVisible(node, field),
    );
  }

  function isTextEntryTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) {
      return false;
    }

    return Boolean(
      target.closest(
        'input:not([type="button"]):not([type="checkbox"]):not([type="radio"]), textarea, select, [contenteditable="true"]',
      ),
    );
  }

  function readExecutionInputData(): Record<string, unknown> {
    return {};
  }

  function renderSettingsPanel(): void {
    const settingsNode = getNode(getSettingsNodeId());
    const nodeDefinition = getNodeDefinition(settingsNode);
    if (!settingsNode || !nodeDefinition) {
      canvas.settingsPanel.hidden = true;
      canvas.settingsFields.innerHTML = '';
      renderExecutionNodeAction();
      return;
    }

    const activeSettingsNode = settingsNode;
    const activeNodeDefinition = nodeDefinition;
    const availableInputPaths = getAvailableInputPaths({
      executionInputData: readExecutionInputData(),
      getNode,
      nodeId: activeSettingsNode.id,
      workflowDefinition,
    });
    const fieldMarkup = renderNodeSettingsFieldsMarkup({
      availableInputPaths,
      getFieldOptions: (field) => getFieldOptionsWithCurrentValue(activeSettingsNode, field),
      getNodeTargetOptions: () => getNodeTargetOptions(activeSettingsNode, workflowDefinition),
      node: activeSettingsNode,
      nodeDefinition: activeNodeDefinition,
    });

    const description = nodeDefinition.description || nodeDefinition.label;
    canvas.settingsPanel.hidden = false;
    canvas.settingsTitle.textContent = settingsNode.label || nodeDefinition.label;
    canvas.settingsDescription.textContent = description;
    canvas.settingsFields.innerHTML = `
      ${renderSettingsOverviewSection({
        nodeDefinitionLabel: nodeDefinition.label,
        nodeId: settingsNode.id,
      })}
      ${renderSettingsIdentitySection({
        nodeId: settingsNode.id,
        nodeLabel: settingsNode.label,
      })}
      ${fieldMarkup || '<div class="workflow-editor-settings-empty">No editable settings for this node yet.</div>'}
    `;
    renderExecutionNodeAction();
  }

  function getNodeContextMenuPosition(clientX: number, clientY: number): { x: number; y: number } {
    const localPoint = viewportController.getBoardLocalPoint(clientX, clientY);
    const rawX = localPoint.x + NODE_CONTEXT_MENU_OFFSET_X;
    const rawY = localPoint.y + NODE_CONTEXT_MENU_OFFSET_Y;
    const minX = NODE_CONTEXT_MENU_MARGIN;
    const minY = NODE_CONTEXT_MENU_MARGIN;
    const maxX = Math.max(
      minX,
      canvas.board.clientWidth - NODE_CONTEXT_MENU_WIDTH - NODE_CONTEXT_MENU_MARGIN,
    );
    const maxY = Math.max(
      minY,
      canvas.board.clientHeight - NODE_CONTEXT_MENU_HEIGHT - NODE_CONTEXT_MENU_MARGIN,
    );

    return {
      x: clamp(Math.round(rawX), minX, maxX),
      y: clamp(Math.round(rawY), minY, maxY),
    };
  }

  function renderNodeContextMenu(): void {
    const contextMenuState = getContextMenuState();
    if (!contextMenuState) {
      canvas.nodeMenu.hidden = true;
      canvas.nodeMenu.innerHTML = '';
      return;
    }

    const node = getNode(contextMenuState.nodeId);
    if (!node) {
      clearContextMenuState();
      canvas.nodeMenu.hidden = true;
      canvas.nodeMenu.innerHTML = '';
      return;
    }

    const title = node.label || formatKindLabel(node.kind) || node.type;
    const nodeDefinition = getNodeDefinition(node);
    const meta = [
      formatKindLabel(node.kind),
      nodeDefinition?.catalog_section === 'apps'
      && getRealAppLabel(nodeDefinition)
      && getRealAppLabel(nodeDefinition) !== 'Workflow'
        ? getRealAppLabel(nodeDefinition)
        : null,
    ]
      .filter((value): value is string => Boolean(value))
      .join(' • ');
    canvas.nodeMenu.hidden = false;
    canvas.nodeMenu.style.left = `${contextMenuState.x}px`;
    canvas.nodeMenu.style.top = `${contextMenuState.y}px`;
    canvas.nodeMenu.innerHTML = renderNodeContextMenuMarkup({ meta, title });
  }

  function renderEmptyState(): void {
    const emptyWorkflow = isEmptyWorkflow();
    canvas.board.classList.toggle('is-empty-workflow', emptyWorkflow);
    canvas.emptyState.hidden = !emptyWorkflow;
  }

  function renderCanvasHud(): void {
    const viewport = viewportController.getViewport();
    canvas.fitViewButton.disabled = workflowDefinition.nodes.length === 0;
    canvas.zoomLabel.textContent = `${Math.round(viewport.zoom * 100)}%`;
    canvas.zoomOutButton.disabled = viewport.zoom <= 0.46;
    canvas.zoomInButton.disabled = viewport.zoom >= 1.79;
  }

  function repositionGraph(anchorNodeId?: string): void {
    const graphBounds = getGraphBounds(workflowDefinition.nodes);
    if (!graphBounds) {
      return;
    }

    const anchorNode = anchorNodeId ? getNode(anchorNodeId) : null;
    if (anchorNode) {
      viewportController.focusPoint(getNodeCenter(anchorNode));
      return;
    }

    viewportController.fitBounds(graphBounds, { padding: 104 });
  }

  function renderNodes(): void {
    canvas.nodeLayer.innerHTML = workflowDefinition.nodes
      .map((node) => {
        const nodeDefinition = nodeRegistry.definitionMap.get(node.type);
        return renderWorkflowEditorNodeMarkup(
          buildWorkflowEditorNodePresentation({
            activeExecutionNodeId: getActiveExecutionNodeId(),
            auxiliaryPortDefinitions: AGENT_AUXILIARY_PORTS,
            canNodeEmitConnections,
            canNodeReceiveConnections,
            connectionDraft,
            connectorSides: CONNECTOR_SIDES,
            executionActiveNodeIds: getExecutionActiveNodeIds(),
            executionFailedNodeIds: getExecutionFailedNodeIds(),
            executionSucceededNodeId: getExecutionSucceededNodeId(),
            getCompatibleAgentAuxiliaryPort,
            getNode,
            getNodeDefinition,
            isExecutionPending: getIsExecutionPending(),
            isValidConnection,
            node,
            nodeDefinition,
            selectedNodeId: getSelectedNodeId(),
            workflowDefinition,
          }),
        );
      })
      .join('');

    workflowDefinition.nodes.forEach((node) => {
      const nodeElement = getNodeElement(canvas.nodeLayer, node.id);
      if (nodeElement) {
        setNodeElementPosition(nodeElement, node);
      }
    });
  }

  function renderEdges(): void {
    canvas.edgeLayer.setAttribute(
      'viewBox',
      `0 0 ${Math.max(canvas.board.clientWidth, 1)} ${Math.max(canvas.board.clientHeight, 1)}`,
    );
    const edgePresentation = buildWorkflowEditorEdgesPresentation({
      boardHeight: canvas.board.clientHeight,
      boardWidth: canvas.board.clientWidth,
      connectionDraft,
      dragActive: Boolean(dragState),
      getNode,
      hoveredEdgeId,
      viewportWorldToScreen: viewportController.worldToScreen,
      workflowDefinition,
    });

    canvas.edgeLayer.innerHTML = renderWorkflowEditorEdgesMarkup(edgePresentation);
    canvas.edgeControls.innerHTML = edgePresentation.hoveredControl
      ? renderEdgeRemoveButtonMarkup(edgePresentation.hoveredControl)
      : '';
  }

  function renderCanvas(): void {
    renderNodes();
    renderEdges();
    renderEmptyState();
    renderCanvasHud();
    renderNodeContextMenu();
  }

  function cancelConnection(): void {
    connectionDraft = null;
    renderCanvas();
  }

  const {
    cleanupDeletedNode,
    clearContextMenuState,
    closeNodeContextMenu,
    closeNodeSettings,
    getContextMenuState,
    getSelectedNodeId,
    getSettingsNodeId,
    hasOpenContextMenu,
    openNodeContextMenu,
    openNodeSettings,
    setSelectedNodeId,
    setSettingsNodeId,
  } = createWorkflowDesignerSelectionController({
    getContextMenuPosition: getNodeContextMenuPosition,
    getNode: (nodeId) => getNode(nodeId ?? null),
    renderCanvas,
    renderNodeContextMenu,
    renderSettingsPanel,
  });

  const {
    executeDesignerRun,
    getActiveExecutionNodeId,
    getExecutionActiveNodeIds,
    getExecutionFailedNodeIds,
    getExecutionSucceededNodeId,
    getIsExecutionPending,
    renderExecutionNodeAction,
  } = createWorkflowDesignerExecutionController({
    buildExecutionRequestBody,
    csrfToken,
    execution,
    getInitialExecutionNodeId,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getSelectedNodeId,
    getSettingsNodeId,
    isTerminalRunStatus,
    onExecutionStateChange: () => {
      renderCanvas();
      renderSettingsPanel();
    },
    openNodeSettings,
  });

  const {
    closeBrowser,
    getInsertDraft,
    getIsBrowserOpen,
    goBackBrowserView,
    navigateBrowser,
    openAuxiliaryInsertBrowser,
    openBrowser,
    openInsertBrowser,
    renderBrowser,
    setSearchQuery,
    showEmptyWorkflowBrowser,
  } = createWorkflowDesignerBrowserController({
    board: canvas.board,
    browser,
    clearContextMenuState,
    clearSettingsNodeId: () => setSettingsNodeId(null),
    definitions: nodeRegistry.definitions,
    getAvailableSections: () => getAvailablePaletteSections(nodeRegistry, workflowDefinition),
    getIsEmptyWorkflow: isEmptyWorkflow,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getWorkflowDefinition: () => workflowDefinition,
    initialIsOpen: workflowDefinition.nodes.length === 0,
    initialView: getDefaultBrowserView(workflowDefinition.nodes.length === 0),
    openNodeSettings,
    renderCanvas,
    renderNodeContextMenu,
    renderSettingsPanel,
    screenToWorld: viewportController.screenToWorld,
    setSelectedNodeId: (nodeId) => setSelectedNodeId(nodeId),
  });

  const {
    addEdge,
    deleteNode,
    removeEdge,
    syncNodeTargetEdges,
  } = createWorkflowDesignerGraphController({
    createEdgeId: () => createId('edge'),
    getNode: (nodeId) => getNode(nodeId ?? null),
    getNodeDefinition,
    getWorkflowDefinition: () => workflowDefinition,
    getVisibleTargetFields,
    graphStore,
    isValidConnection,
    onClearHoveredEdge: () => {
      hoveredEdgeId = null;
    },
    onDeleteNodeStateCleanup: (nodeId) => {
      cleanupDeletedNode(nodeId);
      if (connectionDraft?.sourceId === nodeId) {
        connectionDraft = null;
      }
      hoveredEdgeId = null;
    },
    renderBrowser,
    renderCanvas,
    renderSettingsPanel,
    showEmptyWorkflowBrowser,
    syncDefinitionInput,
  });

  function shouldOpenInsertBrowser(clientX: number, clientY: number): boolean {
    const target = document.elementFromPoint(clientX, clientY) as HTMLElement | null;
    if (!target) {
      return false;
    }

    if (
      target.closest('[data-node-browser]') ||
      target.closest('[data-open-node-browser]') ||
      target.closest('[data-workflow-settings-panel]') ||
      target.closest('[data-workflow-node-id]')
    ) {
      return false;
    }

    return Boolean(target.closest('[data-workflow-board]'));
  }

  function addNode(nodeType: string): void {
    const nodeDefinition = nodeRegistry.definitionMap.get(nodeType);
    if (!nodeDefinition) {
      return;
    }

    const pendingInsert = getInsertDraft();
    const newNode = createWorkflowNode(
      canvas.board,
      workflowDefinition,
      nodeDefinition,
      getSelectedNodeId(),
      pendingInsert?.position,
    );
    graphStore.addNode(newNode);
    setSelectedNodeId(newNode.id);
    syncDefinitionInput();
    closeBrowser();
    if (pendingInsert?.sourceId) {
      addEdge(pendingInsert.sourceId, newNode.id);
      setSettingsNodeId(newNode.id);
    } else if (pendingInsert?.targetId && pendingInsert.targetPort) {
      addEdge(newNode.id, pendingInsert.targetId, {
        sourcePort: pendingInsert.targetPort,
        targetPort: pendingInsert.targetPort,
      });
      setSettingsNodeId(newNode.id);
    }
    renderCanvas();
    renderBrowser();
    renderSettingsPanel();
  }

  const {
    applyNodeSettingSuggestion,
    updateSelectedNodeField,
    updateSelectedNodeFieldMode,
    updateSelectedNodeLabel,
  } = createWorkflowDesignerSettingsController({
    canvas,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getNodeDefinition,
    getSettingsNodeId,
    renderCanvas,
    renderSettingsPanel,
    syncDefinitionInput,
    syncNodeTargetEdges,
  });

  function beginConnection(sourceId: string, pointerId: number, clientX: number, clientY: number): void {
    const sourceNode = getNode(sourceId);
    const sourceDefinition = getNodeDefinition(sourceNode);
    if (!sourceNode || !canNodeEmitConnections(sourceNode, workflowDefinition.edges, sourceDefinition)) {
      return;
    }

    const pointerPoint = getPointFromClient(clientX, clientY);
    setSelectedNodeId(sourceId);
    hoveredEdgeId = null;
    connectionDraft = {
      hoveredTargetId: null,
      hoveredTargetPort: null,
      hoveredTargetSide: null,
      pointerId,
      pointerX: pointerPoint.x,
      pointerY: pointerPoint.y,
      sourceId,
    };
    renderCanvas();
  }

  function updateNodePosition(nodeId: string, position: { x: number; y: number }): void {
    const node = workflowDefinition.nodes.find((item) => item.id === nodeId);
    if (!node) {
      return;
    }

    node.position = clampNodePosition(
      canvas.board,
      position,
      getNodeRenderHeight(node),
      getNodeRenderWidth(node),
    );
    syncDefinitionInput();

    const nodeElement = getNodeElement(canvas.nodeLayer, nodeId);
    if (nodeElement) {
      setNodeElementPosition(nodeElement, node);
    }

    renderEdges();
  }

  registerWorkflowDesignerPointerInteractions({
    addEdge,
    beginConnection,
    canvas,
    closeNodeContextMenu,
    getConnectionDraft: () => connectionDraft,
    getDragState: () => dragState,
    getHoveredEdgeId: () => hoveredEdgeId,
    getHoveredTarget,
    getNode: (nodeId) => getNode(nodeId),
    getNodeElement: (nodeId) => getNodeElement(canvas.nodeLayer, nodeId),
    getPanState: () => panState,
    getPointFromClient,
    getSelectedNodeId,
    getSettingsNodeId,
    hasOpenContextMenu,
    isValidConnection,
    openInsertBrowser,
    openNodeContextMenu,
    renderCanvas,
    renderEdges,
    renderNodes,
    renderSettingsPanel,
    setConnectionDraft: (nextState) => {
      connectionDraft = nextState;
    },
    setDragState: (nextState) => {
      dragState = nextState;
    },
    setHoveredEdgeId: (nextState) => {
      hoveredEdgeId = nextState;
    },
    setPanState: (nextState) => {
      panState = nextState;
    },
    setSelectedNodeId,
    setSettingsNodeId,
    shouldOpenInsertBrowser,
    updateNodePosition,
    viewportController,
  });

  registerWorkflowDesignerUiBindings({
    addNode,
    applyNodeSettingSuggestion,
    browser,
    canvas,
    cancelConnection,
    closeBrowser,
    closeNodeContextMenu,
    closeNodeSettings,
    deleteNode,
    getConnectionDraftActive: () => Boolean(connectionDraft),
    getContextMenuNodeId: () => getContextMenuState()?.nodeId ?? null,
    getIsBrowserOpen,
    getSelectedNodeId,
    getSettingsNodeId,
    goBackBrowserView,
    isTextEntryTarget,
    navigateBrowser,
    openAuxiliaryInsertBrowser,
    openBrowser,
    openNodeSettings,
    removeEdge,
    renderBrowser,
    repositionGraph,
    root,
    runNode: (nodeId) => {
      void executeDesignerRun(getNodeRunUrl(nodeId), { nodeId });
    },
    runSelectedNode: () => {
      const settingsNodeId = getSettingsNodeId();
      if (!settingsNodeId) {
        return;
      }
      void executeDesignerRun(getNodeRunUrl(settingsNodeId), { nodeId: settingsNodeId });
    },
    runWorkflow: () => {
      void executeDesignerRun(workflowRunUrl);
    },
    setSearchQuery,
    updateSelectedNodeField,
    updateSelectedNodeFieldMode,
    updateSelectedNodeLabel,
    zoomByStep: (direction) => {
      viewportController.zoomByStep(direction);
    },
  });

  syncDefinitionInput();
  renderCanvas();
  renderBrowser();
  renderSettingsPanel();
}
