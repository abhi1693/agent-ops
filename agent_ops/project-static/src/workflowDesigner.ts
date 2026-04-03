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
  getAgentAuxiliaryPortPoint,
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
  getAgentAuxiliaryAllowedNodeTypes,
  getAgentAuxiliaryPortDefinition,
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
  renderBrowserState,
  getDefaultBrowserView,
  getPreviousBrowserView,
  type BrowserView,
} from './workflowDesigner/panels/browserState';
import {
  renderSettingsIdentitySection,
  renderNodeSettingsFieldsMarkup,
  renderSettingsOverviewSection,
} from './workflowDesigner/panels/settingsPanel';
import {
  buildTemplateInsertionValue,
  getAvailableInputPaths,
  getNodeSettingControl,
} from './workflowDesigner/panels/settingsAssist';
import {
  buildWorkflowEditorNodePresentation,
  getFieldOptionsWithCurrentValue,
} from './workflowDesigner/presenters/nodePresentation';
import { buildWorkflowEditorEdgesPresentation } from './workflowDesigner/presenters/edgePresentation';
import { buildNodeRegistry, getAvailablePaletteSections } from './workflowDesigner/registry/nodeRegistry';
import { normalizeWorkflowDefinition, serializeWorkflowDefinition } from './workflowDesigner/schema/workflowSchema';
import { createGraphStore } from './workflowDesigner/state/graphStore';
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
  getRuntimeTemplateFieldInputModeDefault,
  getTemplateFieldInputMode,
  getTemplateFieldOptions,
  getTemplateFieldValue,
  isTemplateFieldVisible,
  parseJsonScript,
  supportsTemplateFieldInputMode,
  WORKFLOW_NODE_INPUT_MODES_KEY,
} from './workflowDesigner/utils';
import { createViewportController } from './workflowDesigner/viewport/controller';

type InsertDraft = {
  allowedNodeTypes?: string[];
  position: {
    x: number;
    y: number;
  };
  sourceId?: string;
  targetId?: string;
  targetPort?: AgentAuxiliaryPortId;
};

type ContextMenuState = {
  nodeId: string;
  x: number;
  y: number;
};

type DesignerRunResponse = {
  message: string;
  mode: string;
  node?: {
    id: string;
    kind: string;
    label: string;
    type: string;
  };
  poll_url?: string;
  run: {
    active_node_ids: string[];
    badge_class: string;
    context_json: string | null;
    error: string;
    failed_node_ids: string[];
    id: number;
    input_json: string | null;
    last_completed_node_id: string | null;
    output_json: string | null;
    status: string;
    step_count: number;
    steps_json: string | null;
    trigger_mode: string;
    workflow_version: number;
  };
};

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

  let isBrowserOpen = workflowDefinition.nodes.length === 0;
  let browserView: BrowserView = workflowDefinition.nodes.length === 0
    ? { kind: 'trigger-root' }
    : { kind: 'next-step-root' };
  let searchQuery = '';
  let selectedNodeId: string | null = null;
  let settingsNodeId: string | null = null;
  let dragState: DragState | null = null;
  let panState: PanState | null = null;
  let connectionDraft: ConnectionDraft | null = null;
  let contextMenuState: ContextMenuState | null = null;
  let hoveredEdgeId: string | null = null;
  let insertDraft: InsertDraft | null = null;
  let isExecutionPending = false;
  let activeExecutionNodeId: string | null = null;
  let executionActiveNodeIds: string[] = [];
  let executionFailedNodeIds: string[] = [];
  let executionSucceededNodeId: string | null = null;

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

  function setExecutionStatus(label: string, badgeClass = 'text-bg-secondary'): void {
    if (!execution) {
      return;
    }

    execution.status.textContent = label;
    execution.status.className = `badge ${badgeClass}`;
  }

  function renderExecutionNodeAction(): void {
    if (!execution?.nodeRunButton) {
      return;
    }

    const settingsNode = getNode(settingsNodeId);
    if (!settingsNode) {
      execution.nodeRunButton.hidden = true;
      execution.nodeRunButton.disabled = true;
      execution.nodeRunButton.innerHTML = `
        <i class="mdi mdi-play"></i>
        <span class="ms-1">Run node</span>
      `;
      return;
    }

    const isNodeExecutionPending =
      executionActiveNodeIds.includes(settingsNode.id)
      || (isExecutionPending && activeExecutionNodeId === settingsNode.id);
    execution.nodeRunButton.hidden = false;
    execution.nodeRunButton.disabled = isExecutionPending;
    execution.nodeRunButton.innerHTML = `
      <i class="mdi ${isNodeExecutionPending ? 'mdi-loading mdi-spin' : 'mdi-play'}"></i>
      <span class="ms-1">${isNodeExecutionPending ? 'Running node' : 'Run node'}</span>
    `;
  }

  function clearExecutionError(): void {
    if (!execution) {
      return;
    }

    execution.error.hidden = true;
    execution.error.textContent = '';
  }

  function showExecutionError(message: string): void {
    if (!execution) {
      return;
    }

    execution.error.hidden = false;
    execution.error.textContent = message;
  }

  function parseExecutionInput(): Record<string, unknown> | null {
    if (!execution) {
      return {};
    }

    clearExecutionError();
    return {};
  }

  function renderExecutionResult(payload: DesignerRunResponse): void {
    if (!execution) {
      return;
    }

    const statusLabelByRunStatus: Record<string, { badgeClass: string; label: string }> = {
      failed: {
        badgeClass: 'text-bg-danger',
        label: 'Failed',
      },
      pending: {
        badgeClass: 'text-bg-secondary',
        label: 'Queued',
      },
      running: {
        badgeClass: 'text-bg-primary',
        label: 'Running',
      },
      succeeded: {
        badgeClass: 'text-bg-success',
        label: 'Completed',
      },
    };
    const statusPresentation = statusLabelByRunStatus[payload.run.status] ?? {
      badgeClass: 'text-bg-secondary',
      label: payload.run.status,
    };
    executionActiveNodeIds = payload.run.active_node_ids ?? [];
    executionFailedNodeIds = payload.run.failed_node_ids ?? [];
    executionSucceededNodeId = null;
    if (payload.run.status === 'succeeded') {
      executionSucceededNodeId = payload.run.last_completed_node_id;
      executionFailedNodeIds = [];
      executionActiveNodeIds = [];
    } else if (payload.run.status === 'failed') {
      executionActiveNodeIds = [];
    } else if (payload.run.status !== 'running') {
      executionActiveNodeIds = [];
      executionFailedNodeIds = [];
    }
    const modeLabel = payload.mode.startsWith('node')
      ? payload.node?.label ?? 'Node run'
      : 'Workflow run';
    const summaryParts = [
      `Run #${payload.run.id}`,
      `${payload.run.step_count} step${payload.run.step_count === 1 ? '' : 's'}`,
      `v${payload.run.workflow_version}`,
    ];
    if (payload.message) {
      summaryParts.push(payload.message);
    }

    execution.resultEmpty.hidden = true;
    execution.result.hidden = false;
    execution.resultTitle.textContent = modeLabel;
    execution.resultSummary.textContent = summaryParts.join(' · ');
    execution.resultBadge.className = `badge ${payload.run.badge_class}`;
    execution.resultBadge.textContent = payload.run.status;
    execution.resultOutput.textContent = payload.run.output_json ?? '{}';
    execution.resultTrace.textContent = payload.run.steps_json ?? '[]';
    execution.resultContext.textContent = payload.run.context_json ?? '{}';
    if (payload.run.error) {
      execution.resultError.hidden = false;
      execution.resultError.textContent = payload.run.error;
    } else {
      execution.resultError.hidden = true;
      execution.resultError.textContent = '';
    }
    setExecutionStatus(statusPresentation.label, statusPresentation.badgeClass);
    renderCanvas();
    renderSettingsPanel();
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

  async function pollDesignerRunStatus(url: string): Promise<DesignerRunResponse> {
    let lastPayload: DesignerRunResponse | null = null;

    for (let attempt = 0; attempt < 120; attempt += 1) {
      if (attempt > 0) {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
      }

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
      });
      const payload = (await response.json()) as DesignerRunResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(payload && 'detail' in payload && payload.detail ? payload.detail : 'Unable to fetch run status.');
      }

      lastPayload = payload as DesignerRunResponse;
      renderExecutionResult(lastPayload);
      if (isTerminalRunStatus(lastPayload.run.status)) {
        return lastPayload;
      }
    }

    if (lastPayload) {
      return lastPayload;
    }

    throw new Error('Workflow run polling timed out.');
  }

  async function executeDesignerRun(
    url: string,
    options?: {
      nodeId?: string | null;
    },
  ): Promise<void> {
    if (!execution || !url) {
      return;
    }

    const nodeId = options?.nodeId ?? null;
    if (nodeId && settingsNodeId !== nodeId) {
      openNodeSettings(nodeId);
    } else if (!nodeId && !settingsNodeId && selectedNodeId) {
      openNodeSettings(selectedNodeId);
    }

    const inputData = parseExecutionInput();
    if (inputData === null) {
      return;
    }

    isExecutionPending = true;
    activeExecutionNodeId = getInitialExecutionNodeId(nodeId);
    executionActiveNodeIds = activeExecutionNodeId ? [activeExecutionNodeId] : [];
    executionFailedNodeIds = [];
    executionSucceededNodeId = null;
    execution.runButton.disabled = true;
    setExecutionStatus(nodeId ? 'Running node' : 'Running workflow', 'text-bg-primary');
    renderCanvas();
    renderSettingsPanel();

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: buildExecutionRequestBody(inputData),
      });
      const payload = (await response.json()) as DesignerRunResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(payload && 'detail' in payload && payload.detail ? payload.detail : 'Execution failed.');
      }
      const runPayload = payload as DesignerRunResponse;
      renderExecutionResult(runPayload);
      if (runPayload.poll_url && !isTerminalRunStatus(runPayload.run.status)) {
        await pollDesignerRunStatus(runPayload.poll_url);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Execution failed.';
      showExecutionError(message);
      executionActiveNodeIds = [];
      executionFailedNodeIds = [];
      executionSucceededNodeId = null;
      setExecutionStatus('Failed', 'text-bg-danger');
      renderCanvas();
      renderSettingsPanel();
    } finally {
      isExecutionPending = false;
      activeExecutionNodeId = null;
      execution.runButton.disabled = false;
      renderCanvas();
      renderSettingsPanel();
    }
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

  function syncNodeTargetEdges(node: WorkflowNode, nodeDefinition: WorkflowNodeDefinition | undefined): void {
    const targetFields = getVisibleTargetFields(node, nodeDefinition);
    if (!targetFields.length) {
      return;
    }

    const configuredTargetIds = Array.from(
      new Set(
        targetFields
          .map((field) => {
            const value = node.config?.[field.key];
            return typeof value === 'string' && value !== node.id ? value : '';
          })
          .filter((value) => Boolean(value) && Boolean(getNode(value))),
      ),
    );

    graphStore.replaceEdges(workflowDefinition.edges.filter((edge) => edge.source !== node.id));
    configuredTargetIds.forEach((targetId) => {
      graphStore.addEdge({
        id: createId('edge'),
        source: node.id,
        target: targetId,
      });
    });
  }

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

  function getSelectedSettingsField(
    key: string,
  ): { field: WorkflowNodeTemplateField; node: WorkflowNode } | null {
    const settingsNode = getNode(settingsNodeId);
    const nodeDefinition = getNodeDefinition(settingsNode);
    if (!settingsNode || !nodeDefinition) {
      return null;
    }

    const field = nodeDefinition.fields.find((item) => item.key === key);
    if (!field) {
      return null;
    }

    return { field, node: settingsNode };
  }

  function updateSelectedNodeFieldMode(
    key: string,
    mode: 'expression' | 'static',
    options?: { rerenderSettings?: boolean },
  ): void {
    const fieldSelection = getSelectedSettingsField(key);
    if (!fieldSelection || !supportsTemplateFieldInputMode(fieldSelection.field)) {
      return;
    }

    const { field, node } = fieldSelection;
    const nextConfig = { ...(node.config ?? {}) };
    const currentModesValue = nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
    const nextModes =
      currentModesValue && typeof currentModesValue === 'object' && !Array.isArray(currentModesValue)
        ? { ...(currentModesValue as Record<string, unknown>) }
        : {};
    const defaultMode = getRuntimeTemplateFieldInputModeDefault(field);

    if (mode === defaultMode) {
      delete nextModes[key];
    } else {
      nextModes[key] = mode;
    }

    if (Object.keys(nextModes).length > 0) {
      nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY] = nextModes;
    } else {
      delete nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
    }

    node.config = nextConfig;
    syncDefinitionInput();
    renderCanvas();
    if (options?.rerenderSettings) {
      renderSettingsPanel();
    }
  }

  function applyNodeSettingSuggestion(
    key: string,
    value: string,
    binding: string,
  ): void {
    const control = getNodeSettingControl(canvas.settingsFields, key);
    if (!control) {
      return;
    }

    const fieldSelection = getSelectedSettingsField(key);
    if (fieldSelection && supportsTemplateFieldInputMode(fieldSelection.field) && binding === 'template') {
      updateSelectedNodeFieldMode(key, 'expression');
    }

    const nextValue = binding === 'template' && (control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement)
      ? buildTemplateInsertionValue(control, value)
      : value;

    control.value = nextValue;
    updateSelectedNodeField(key, nextValue, { rerenderSettings: true });
  }

  function renderSettingsPanel(): void {
    const settingsNode = getNode(settingsNodeId);
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
      ...getNodeContextMenuPosition(clientX, clientY),
    };
    renderCanvas();
    renderSettingsPanel();
  }

  function renderNodeContextMenu(): void {
    if (!contextMenuState) {
      canvas.nodeMenu.hidden = true;
      canvas.nodeMenu.innerHTML = '';
      return;
    }

    const node = getNode(contextMenuState.nodeId);
    if (!node) {
      contextMenuState = null;
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

  function setBrowserView(nextView: BrowserView): void {
    browserView = nextView;
    searchQuery = '';
    browser.searchInput.value = '';
  }

  function goBackBrowserView(): void {
    const previousView = getPreviousBrowserView(browserView, isEmptyWorkflow());
    if (previousView) {
      setBrowserView(previousView);
      renderBrowser();
    }
  }

  function renderBrowser(): void {
    const insertPort = getAgentAuxiliaryPortDefinition(insertDraft?.targetPort);
    const allowedNodeTypes = insertDraft?.allowedNodeTypes ?? null;
    const filteredSections = getAvailablePaletteSections(nodeRegistry, workflowDefinition)
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
      definitions: nodeRegistry.definitions,
      filteredSections,
      insertPort: insertPort?.id,
      isEmptyWorkflow: isEmptyWorkflow(),
      searchQuery,
    });

    browser.browser.hidden = !isBrowserOpen;
    browser.browser.classList.toggle('is-starter-mode', isEmptyWorkflow());
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
            activeExecutionNodeId,
            auxiliaryPortDefinitions: AGENT_AUXILIARY_PORTS,
            canNodeEmitConnections,
            canNodeReceiveConnections,
            connectionDraft,
            connectorSides: CONNECTOR_SIDES,
            executionActiveNodeIds,
            executionFailedNodeIds,
            executionSucceededNodeId,
            getCompatibleAgentAuxiliaryPort,
            getNode,
            getNodeDefinition,
            isExecutionPending,
            isValidConnection,
            node,
            nodeDefinition,
            selectedNodeId,
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

  function closeBrowser(): void {
    const emptyWorkflow = isEmptyWorkflow();
    isBrowserOpen = false;
    insertDraft = null;
    contextMenuState = null;
    browserView = getDefaultBrowserView(emptyWorkflow);
    searchQuery = '';
    browser.searchInput.value = '';
    renderBrowser();
    renderNodeContextMenu();
  }

  function cancelConnection(): void {
    connectionDraft = null;
    renderCanvas();
  }

  function openBrowser(): void {
    const emptyWorkflow = isEmptyWorkflow();
    isBrowserOpen = true;
    contextMenuState = null;
    setBrowserView(getDefaultBrowserView(emptyWorkflow));
    renderBrowser();
    renderNodeContextMenu();
    window.setTimeout(() => {
      browser.searchInput.focus();
    }, 0);
  }

  function openInsertBrowser(sourceId: string, clientX: number, clientY: number): void {
    const worldPoint = viewportController.screenToWorld(clientX, clientY);
    insertDraft = {
      position: clampNodePosition(canvas.board, {
        x: worldPoint.x - NODE_WIDTH / 2,
        y: worldPoint.y - NODE_HEIGHT / 2,
      }, NODE_HEIGHT),
      sourceId,
    };
    openBrowser();
  }

  function openAuxiliaryInsertBrowser(targetId: string, targetPort: AgentAuxiliaryPortId): void {
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
      allowedNodeTypes: getAgentAuxiliaryAllowedNodeTypes(nodeRegistry.definitions, targetPort),
      position: clampNodePosition(canvas.board, {
        x: portPoint.x - NODE_WIDTH / 2,
        y: targetNode.position.y + targetNodeHeight + 44,
      }, NODE_HEIGHT),
      targetId,
      targetPort,
    };
    selectedNodeId = targetId;
    settingsNodeId = null;
    openBrowser();
    renderCanvas();
    renderSettingsPanel();
  }

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

    const pendingInsert = insertDraft;
    const newNode = createWorkflowNode(
      canvas.board,
      workflowDefinition,
      nodeDefinition,
      selectedNodeId,
      pendingInsert?.position,
    );
    graphStore.addNode(newNode);
    selectedNodeId = newNode.id;
    searchQuery = '';
    browser.searchInput.value = '';
    syncDefinitionInput();
    closeBrowser();
    if (pendingInsert?.sourceId) {
      addEdge(pendingInsert.sourceId, newNode.id);
      settingsNodeId = newNode.id;
    } else if (pendingInsert?.targetId && pendingInsert.targetPort) {
      addEdge(newNode.id, pendingInsert.targetId, {
        sourcePort: pendingInsert.targetPort,
        targetPort: pendingInsert.targetPort,
      });
      settingsNodeId = newNode.id;
    }
    renderCanvas();
    renderBrowser();
    renderSettingsPanel();
  }

  function updateSelectedNodeLabel(value: string, options?: { rerenderSettings?: boolean }): void {
    const settingsNode = getNode(settingsNodeId);
    if (!settingsNode) {
      return;
    }

    settingsNode.label = value;
    syncDefinitionInput();
    renderCanvas();
    if (options?.rerenderSettings) {
      renderSettingsPanel();
      return;
    }

    canvas.settingsTitle.textContent = value || getNodeDefinition(settingsNode)?.label || settingsNode.type;
  }

  function updateSelectedNodeField(
    key: string,
    value: string,
    options?: { rerenderSettings?: boolean },
  ): void {
    const settingsNode = getNode(settingsNodeId);
    const nodeDefinition = getNodeDefinition(settingsNode);
    if (!settingsNode || !nodeDefinition) {
      return;
    }

    const nextConfig = { ...(settingsNode.config ?? {}) };
    if (value === '') {
      delete nextConfig[key];
    } else {
      nextConfig[key] = value;
    }

    const field = nodeDefinition.fields.find((item) => item.key === key);
    if (field && supportsTemplateFieldInputMode(field)) {
      const currentModesValue = nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
      const nextModes =
        currentModesValue && typeof currentModesValue === 'object' && !Array.isArray(currentModesValue)
          ? { ...(currentModesValue as Record<string, unknown>) }
          : {};
      if (value === '') {
        delete nextModes[key];
      } else {
        const runtimeDefaultMode = getRuntimeTemplateFieldInputModeDefault(field);
        const selectedMode = getTemplateFieldInputMode(settingsNode, field);

        if (selectedMode === runtimeDefaultMode) {
          delete nextModes[key];
        } else {
          nextModes[key] = selectedMode;
        }
      }

      if (Object.keys(nextModes).length > 0) {
        nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY] = nextModes;
      } else {
        delete nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
      }
    }

    settingsNode.config = nextConfig;

    syncNodeTargetEdges(settingsNode, getNodeDefinition(settingsNode));
    syncDefinitionInput();
    renderCanvas();
    if (options?.rerenderSettings) {
      renderSettingsPanel();
    }
  }

  function addEdge(
    sourceId: string,
    targetId: string,
    options?: {
      sourcePort?: AgentAuxiliaryPortId;
      targetPort?: AgentAuxiliaryPortId;
    },
  ): void {
    if (!isValidConnection(sourceId, targetId, options?.targetPort ?? null)) {
      return;
    }

    const sourceNode = getNode(sourceId);
    const sourceDefinition = getNodeDefinition(sourceNode);
    const isAuxiliaryEdge = Boolean(options?.targetPort);
    const targetFields = sourceNode && sourceDefinition && !isAuxiliaryEdge
      ? getVisibleTargetFields(sourceNode, sourceDefinition)
      : [];
    if (sourceNode && targetFields.length > 0) {
      const nextConfig = { ...(sourceNode.config ?? {}) };
      const assignedField = targetFields.find((field) => {
        const currentValue = typeof nextConfig[field.key] === 'string' ? String(nextConfig[field.key]) : '';
        return currentValue === '' || currentValue === targetId;
      });

      if (!assignedField) {
        return;
      }

      nextConfig[assignedField.key] = targetId;
      sourceNode.config = nextConfig;
    }

    graphStore.addEdge({
      id: createId('edge'),
      source: sourceId,
      ...(options?.sourcePort ? { sourcePort: options.sourcePort } : {}),
      target: targetId,
      ...(options?.targetPort ? { targetPort: options.targetPort } : {}),
    });

    if (sourceNode && !isAuxiliaryEdge) {
      syncNodeTargetEdges(sourceNode, sourceDefinition);
    }
    syncDefinitionInput();
    renderCanvas();
    renderSettingsPanel();
  }

  function removeEdge(edgeId: string): void {
    const edge = workflowDefinition.edges.find((item) => item.id === edgeId);
    if (!edge) {
      return;
    }

    const sourceNode = getNode(edge.source);
    const sourceDefinition = getNodeDefinition(sourceNode);
    const targetFields = sourceNode && sourceDefinition && !edge.targetPort
      ? getVisibleTargetFields(sourceNode, sourceDefinition)
      : [];

    if (sourceNode && targetFields.length > 0) {
      const nextConfig = { ...(sourceNode.config ?? {}) };
      let didRemoveTargetField = false;

      targetFields.forEach((field) => {
        if (nextConfig[field.key] === edge.target) {
          delete nextConfig[field.key];
          didRemoveTargetField = true;
        }
      });

      if (didRemoveTargetField) {
        sourceNode.config = nextConfig;
        syncNodeTargetEdges(sourceNode, sourceDefinition);
      } else {
        graphStore.removeEdge(edgeId);
      }
    } else {
      graphStore.removeEdge(edgeId);
    }

    hoveredEdgeId = null;
    syncDefinitionInput();
    renderCanvas();
    renderSettingsPanel();
  }

  function deleteNode(nodeId: string): void {
    const node = getNode(nodeId);
    if (!node) {
      return;
    }

    workflowDefinition.nodes.forEach((candidate) => {
      if (candidate.id === nodeId) {
        return;
      }

      const candidateDefinition = getNodeDefinition(candidate);
      const targetFields = getVisibleTargetFields(candidate, candidateDefinition);
      if (!targetFields.length) {
        return;
      }

      const nextConfig = { ...(candidate.config ?? {}) };
      let didChange = false;
      targetFields.forEach((field) => {
        if (nextConfig[field.key] === nodeId) {
          delete nextConfig[field.key];
          didChange = true;
        }
      });

      if (!didChange) {
        return;
      }

      candidate.config = nextConfig;
      syncNodeTargetEdges(candidate, candidateDefinition);
    });

    graphStore.removeNode(nodeId);

    if (selectedNodeId === nodeId) {
      selectedNodeId = null;
    }
    if (settingsNodeId === nodeId) {
      settingsNodeId = null;
    }
    if (contextMenuState?.nodeId === nodeId) {
      contextMenuState = null;
    }
    if (connectionDraft?.sourceId === nodeId) {
      connectionDraft = null;
    }
    hoveredEdgeId = null;

    if (workflowDefinition.nodes.length === 0) {
      isBrowserOpen = true;
      searchQuery = '';
      browser.searchInput.value = '';
    }

    syncDefinitionInput();
    renderCanvas();
    renderBrowser();
    renderSettingsPanel();
  }

  function beginConnection(sourceId: string, pointerId: number, clientX: number, clientY: number): void {
    const sourceNode = getNode(sourceId);
    const sourceDefinition = getNodeDefinition(sourceNode);
    if (!sourceNode || !canNodeEmitConnections(sourceNode, workflowDefinition.edges, sourceDefinition)) {
      return;
    }

    const pointerPoint = getPointFromClient(clientX, clientY);
    selectedNodeId = sourceId;
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
    getSelectedNodeId: () => selectedNodeId,
    getSettingsNodeId: () => settingsNodeId,
    hasOpenContextMenu: () => Boolean(contextMenuState),
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
    setSelectedNodeId: (nextState) => {
      selectedNodeId = nextState;
    },
    setSettingsNodeId: (nextState) => {
      settingsNodeId = nextState;
    },
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
    getBrowserView: () => browserView,
    getConnectionDraftActive: () => Boolean(connectionDraft),
    getContextMenuNodeId: () => contextMenuState?.nodeId ?? null,
    getIsBrowserOpen: () => isBrowserOpen,
    getSelectedNodeId: () => selectedNodeId,
    getSettingsNodeId: () => settingsNodeId,
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
    runNode: (nodeId) => {
      void executeDesignerRun(getNodeRunUrl(nodeId), { nodeId });
    },
    runSelectedNode: () => {
      if (!settingsNodeId) {
        return;
      }
      void executeDesignerRun(getNodeRunUrl(settingsNodeId), { nodeId: settingsNodeId });
    },
    runWorkflow: () => {
      void executeDesignerRun(workflowRunUrl);
    },
    setBrowserView,
    setSearchQuery: (value) => {
      searchQuery = value;
    },
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
