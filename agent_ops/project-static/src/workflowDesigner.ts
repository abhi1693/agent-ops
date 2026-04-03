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
  buildConnectionPath,
  clampNodePosition,
  getAgentAuxiliaryPortPoint,
  getConnectorPoint,
  getEdgeAnchors,
  getGraphBounds,
  getConnectionMidpoint,
  getNodeCenter,
  getNodeRenderHeight,
  getNodeRenderWidth,
  getOppositeConnectorSide,
  getPreferredConnectorSide,
  getSuggestedNodePosition,
} from './workflowDesigner/geometry';
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
import { buildNodeRegistry, getAvailablePaletteSections } from './workflowDesigner/registry/nodeRegistry';
import {
  isModelDefinition,
  isToolCompatibleDefinition,
} from './workflowDesigner/registry/modelDefinitions';
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

type DragState = {
  nodeId: string;
  offsetX: number;
  offsetY: number;
  pointerId: number;
};

type PanState = {
  didMove: boolean;
  lastClientX: number;
  lastClientY: number;
  pointerId: number;
};

type ConnectionDraft = {
  hoveredTargetId: string | null;
  hoveredTargetPort: AgentAuxiliaryPortId | null;
  hoveredTargetSide: ConnectorSide | null;
  pointerId: number;
  pointerX: number;
  pointerY: number;
  sourceId: string;
};

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
const AGENT_AUXILIARY_PORTS: Array<{
  id: AgentAuxiliaryPortId;
  label: string;
}> = [
  {
    id: 'ai_languageModel',
    label: 'Model',
  },
  {
    id: 'ai_tool',
    label: 'Tools',
  },
];
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

function getDefinitionField(
  definition: WorkflowNodeDefinition | undefined,
  key: string,
): WorkflowNodeTemplateField | undefined {
  return definition?.fields.find((field) => field.key === key);
}

function getFieldOptionsWithCurrentValue(
  node: WorkflowNode,
  field: WorkflowNodeTemplateField,
): WorkflowNodeTemplateOption[] {
  const options = getTemplateFieldOptions(node, field);
  if (field.type !== 'select') {
    return options;
  }

  const currentValue = getTemplateFieldValue(node, field);
  if (!currentValue || options.some((option) => option.value === currentValue)) {
    return options;
  }

  return [
    {
      label: `Current custom (${currentValue})`,
      value: currentValue,
    },
    ...options,
  ];
}

function getEffectiveModelLabel(
  node: WorkflowNode | undefined,
  definition: WorkflowNodeDefinition | undefined,
): string {
  if (!node) {
    return '';
  }

  const customModel = getConfigString(node.config, 'custom_model').trim();
  if (customModel) {
    return customModel;
  }

  const configuredModel = getConfigString(node.config, 'model').trim();
  if (!configuredModel) {
    return '';
  }

  const modelField = getDefinitionField(definition, 'model');
  if (!modelField) {
    return configuredModel;
  }

  const matchedOption = getFieldOptionsWithCurrentValue(node, modelField).find(
    (option) => option.value === configuredModel,
  );
  return matchedOption?.label ?? configuredModel;
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

function getPrimaryIncomingConnectionLimit(
  node: WorkflowNode,
  definition?: WorkflowNodeDefinition,
): number | null {
  if ((definition?.kind ?? node.kind) === 'trigger') {
    return 0;
  }

  return null;
}

function getPrimaryOutgoingConnectionLimit(
  node: WorkflowNode,
  definition?: WorkflowNodeDefinition,
): number | null {
  const resolvedKind = definition?.kind ?? node.kind;
  if (resolvedKind === 'response') {
    return 0;
  }

  const targetFieldCount = definition?.fields.filter((field) => field.type === 'node_target').length ?? 0;
  if (targetFieldCount > 0) {
    return targetFieldCount;
  }

  if (resolvedKind === 'trigger' || resolvedKind === 'agent' || resolvedKind === 'tool') {
    return 1;
  }

  return null;
}

function countPrimaryIncomingConnections(edges: WorkflowDefinition['edges'], nodeId: string): number {
  return edges.filter((edge) => edge.target === nodeId && !edge.targetPort).length;
}

function countPrimaryOutgoingConnections(edges: WorkflowDefinition['edges'], nodeId: string): number {
  return edges.filter((edge) => edge.source === nodeId && !edge.targetPort).length;
}

function canNodeReceiveConnections(
  node: WorkflowNode,
  edges: WorkflowDefinition['edges'],
  definition?: WorkflowNodeDefinition,
): boolean {
  const limit = getPrimaryIncomingConnectionLimit(node, definition);
  if (limit === null) {
    return true;
  }

  return countPrimaryIncomingConnections(edges, node.id) < limit;
}

function canNodeEmitConnections(
  node: WorkflowNode,
  edges: WorkflowDefinition['edges'],
  definition?: WorkflowNodeDefinition,
): boolean {
  const limit = getPrimaryOutgoingConnectionLimit(node, definition);
  if (limit === null) {
    return true;
  }

  return countPrimaryOutgoingConnections(edges, node.id) < limit;
}

function getCompatibleAgentAuxiliaryPort(
  sourceNode: WorkflowNode | undefined,
  sourceDefinition: WorkflowNodeDefinition | undefined,
  targetNode: WorkflowNode | undefined,
): AgentAuxiliaryPortId | null {
  if (!sourceNode || !targetNode || targetNode.kind !== 'agent') {
    return null;
  }

  if (isModelDefinition(sourceDefinition)) {
    return 'ai_languageModel';
  }
  if (sourceNode.kind === 'tool') {
    return 'ai_tool';
  }
  return null;
}

function getAgentAuxiliaryPortDefinition(
  portId: AgentAuxiliaryPortId | null | undefined,
): (typeof AGENT_AUXILIARY_PORTS)[number] | undefined {
  if (!portId) {
    return undefined;
  }

  return AGENT_AUXILIARY_PORTS.find((port) => port.id === portId);
}

function getAgentAuxiliaryAllowedNodeTypes(
  definitions: WorkflowNodeDefinition[],
  portId: AgentAuxiliaryPortId,
): string[] {
  return definitions
    .filter((definition) =>
      portId === 'ai_languageModel'
        ? isModelDefinition(definition)
        : isToolCompatibleDefinition(definition),
    )
    .map((definition) => definition.type);
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
      renderEdgeControls();
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

  function hasConnection(sourceId: string, targetId: string, targetPort?: string | null): boolean {
    return workflowDefinition.edges.some(
      (edge) =>
        edge.source === sourceId &&
        edge.target === targetId &&
        (edge.targetPort ?? null) === (targetPort ?? null),
    );
  }

  function isEmptyWorkflow(): boolean {
    return workflowDefinition.nodes.length === 0;
  }

  function isValidConnection(
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ): boolean {
    const sourceNode = getNode(sourceId);
    const targetNode = getNode(targetId);
    if (!sourceNode || !targetNode || sourceId === targetId) {
      return false;
    }

    const sourceNodeDefinition = getNodeDefinition(sourceNode);
    const compatibleAuxiliaryPort = getCompatibleAgentAuxiliaryPort(sourceNode, sourceNodeDefinition, targetNode);
    if (targetPort) {
      if (compatibleAuxiliaryPort !== targetPort) {
        return false;
      }

      if (hasConnection(sourceId, targetId, targetPort)) {
        return false;
      }

      if (targetPort === 'ai_languageModel') {
        return !workflowDefinition.edges.some(
          (edge) => edge.target === targetId && edge.targetPort === targetPort,
        );
      }

      return true;
    }

    if (compatibleAuxiliaryPort) {
      return false;
    }

    const sourceDefinition = getNodeDefinition(sourceNode);
    const targetDefinition = getNodeDefinition(targetNode);
    if (
      !canNodeEmitConnections(sourceNode, workflowDefinition.edges, sourceDefinition)
      || !canNodeReceiveConnections(targetNode, workflowDefinition.edges, targetDefinition)
    ) {
      return false;
    }

    return !hasConnection(sourceId, targetId, null);
  }

  function getPointFromClient(clientX: number, clientY: number): Point {
    return viewportController.screenToWorld(clientX, clientY);
  }

  function getHoveredTarget(
    clientX: number,
    clientY: number,
    sourceId: string,
  ): { nodeId: string; side: ConnectorSide; targetPort: AgentAuxiliaryPortId | null } | null {
    const target = document.elementFromPoint(clientX, clientY) as HTMLElement | null;
    const auxiliaryPort = target?.closest<HTMLElement>('[data-workflow-node-aux-port]');
    const auxiliaryTargetId = auxiliaryPort?.dataset.workflowNodeAuxNode ?? null;
    const auxiliaryTargetPort = (auxiliaryPort?.dataset.workflowNodeAuxPort as AgentAuxiliaryPortId | undefined) ?? null;
    if (
      auxiliaryTargetId &&
      auxiliaryTargetPort &&
      isValidConnection(sourceId, auxiliaryTargetId, auxiliaryTargetPort)
    ) {
      return {
        nodeId: auxiliaryTargetId,
        side: 'top',
        targetPort: auxiliaryTargetPort,
      };
    }

    const connector = target?.closest<HTMLElement>('[data-workflow-node-connector]');
    const nodeElement = target?.closest<HTMLElement>('[data-workflow-node-id]');
    const targetId = connector?.dataset.workflowNodeConnector ?? nodeElement?.dataset.workflowNodeId ?? null;

    if (!targetId || !isValidConnection(sourceId, targetId)) {
      return null;
    }

    const targetNode = getNode(targetId);
    if (!targetNode) {
      return null;
    }

    return {
      nodeId: targetId,
      side:
        (connector?.dataset.workflowNodeConnectorSide as ConnectorSide | undefined) ??
        getPreferredConnectorSide(targetNode, getPointFromClient(clientX, clientY)),
      targetPort: null,
    };
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
    canvas.nodeMenu.innerHTML = `
      <div class="workflow-editor-node-menu-sheet">
        <div class="workflow-editor-node-menu-head">
          <div class="workflow-editor-node-menu-title">${escapeHtml(title)}</div>
          ${meta ? `<div class="workflow-editor-node-menu-meta">${escapeHtml(meta)}</div>` : ''}
        </div>
        <div class="workflow-editor-node-menu-divider" aria-hidden="true"></div>
        <button
          type="button"
          class="workflow-editor-node-menu-action"
          data-node-menu-action="settings"
        >
          <span class="workflow-editor-node-menu-action-icon" aria-hidden="true">
            <i class="mdi mdi-tune-variant"></i>
          </span>
          <span class="workflow-editor-node-menu-action-label">Settings</span>
        </button>
        <button
          type="button"
          class="workflow-editor-node-menu-action is-danger"
          data-node-menu-action="delete"
        >
          <span class="workflow-editor-node-menu-action-icon" aria-hidden="true">
            <i class="mdi mdi-trash-can-outline"></i>
          </span>
          <span class="workflow-editor-node-menu-action-label">Delete</span>
          <span class="workflow-editor-node-menu-action-shortcut" aria-hidden="true">Del</span>
        </button>
      </div>
    `;
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
        const icon = nodeDefinition?.icon ?? 'mdi-vector-square';
        const title = node.label || nodeDefinition?.label || formatKindLabel(node.kind) || node.type;
        const isDefaultAgentTitle = node.kind === 'agent' && title === (nodeDefinition?.label ?? 'Agent');
        const agentDisplayTitle = node.kind === 'agent' && isDefaultAgentTitle ? 'AI Agent' : title;
        const showAgentKindLabel = node.kind === 'agent' && !isDefaultAgentTitle;
        const isSelected = selectedNodeId === node.id;
        const isNodeExecutionPending =
          executionActiveNodeIds.includes(node.id)
          || (isExecutionPending && activeExecutionNodeId === node.id);
        const isNodeExecutionSucceeded = executionSucceededNodeId === node.id;
        const isNodeExecutionFailed = executionFailedNodeIds.includes(node.id);
        const isConnectionSource = connectionDraft?.sourceId === node.id;
        const isConnectionCandidate = connectionDraft
          ? isValidConnection(connectionDraft.sourceId, node.id)
          : false;
        const isConnectionTarget = connectionDraft?.hoveredTargetId === node.id;
        const sourceConnectionNode = connectionDraft ? getNode(connectionDraft.sourceId) : undefined;
        const sourceConnectionDefinition = getNodeDefinition(sourceConnectionNode);
        const compatibleAuxiliaryPort = connectionDraft
          ? getCompatibleAgentAuxiliaryPort(sourceConnectionNode, sourceConnectionDefinition, node)
          : null;
        const canReceiveConnections = canNodeReceiveConnections(node, workflowDefinition.edges, nodeDefinition);
        const canEmitConnections = canNodeEmitConnections(node, workflowDefinition.edges, nodeDefinition);
        const shouldRenderConnectors = canEmitConnections || (Boolean(connectionDraft) && canReceiveConnections);
        const draftTargetPoint =
          connectionDraft && isConnectionSource
            ? connectionDraft.hoveredTargetId
              ? (() => {
                  const hoveredNode = getNode(connectionDraft.hoveredTargetId);
                  return hoveredNode
                    ? connectionDraft.hoveredTargetPort
                      ? getAgentAuxiliaryPortPoint(hoveredNode, connectionDraft.hoveredTargetPort)
                      : connectionDraft.hoveredTargetSide
                      ? getConnectorPoint(hoveredNode, connectionDraft.hoveredTargetSide)
                      : getNodeCenter(hoveredNode)
                    : {
                        x: connectionDraft.pointerX,
                        y: connectionDraft.pointerY,
                      };
                })()
              : {
                  x: connectionDraft.pointerX,
                  y: connectionDraft.pointerY,
                }
            : null;
        const activeSourceSide =
          draftTargetPoint && canEmitConnections
            ? getPreferredConnectorSide(node, draftTargetPoint)
            : null;
        const activeTargetSide =
          isConnectionTarget && !connectionDraft?.hoveredTargetPort && canReceiveConnections && sourceConnectionNode
            ? connectionDraft?.hoveredTargetSide ?? getPreferredConnectorSide(node, getNodeCenter(sourceConnectionNode))
            : null;
        const connectorModeClass = canReceiveConnections && canEmitConnections
          ? ' is-bidirectional'
          : canEmitConnections
            ? ' is-output-only'
            : ' is-input-only';
        const modelConnections = workflowDefinition.edges.filter(
          (edge) => edge.target === node.id && edge.targetPort === 'ai_languageModel',
        );
        const toolConnections = workflowDefinition.edges.filter(
          (edge) => edge.target === node.id && edge.targetPort === 'ai_tool',
        );
        const agentNeedsModel = node.kind === 'agent' && modelConnections.length === 0;
        const connectors = shouldRenderConnectors
          ? CONNECTOR_SIDES.map((side) => {
              const isActiveSourceConnector = activeSourceSide === side;
              const isActiveTargetConnector = activeTargetSide === side;

              return `
                <span
                  class="workflow-editor-node-connector workflow-editor-node-connector--${side}${connectorModeClass}${isConnectionCandidate ? ' is-candidate' : ''}${isActiveSourceConnector ? ' is-output-active' : ''}${isActiveTargetConnector ? ' is-input-active' : ''}"
                  data-workflow-node-connector="${escapeHtml(node.id)}"
                  data-workflow-node-connector-side="${side}"
                  aria-hidden="true"
                ></span>
              `;
            }).join('')
          : '';
        const executionIndicatorMarkup = isNodeExecutionPending
          ? `
            <span
              class="workflow-editor-node-execution-indicator is-running"
              aria-label="Node running"
              title="Node running"
            >
              <i class="mdi mdi-loading mdi-spin"></i>
            </span>
          `
          : isNodeExecutionSucceeded
            ? `
              <span
                class="workflow-editor-node-execution-indicator is-succeeded"
                aria-label="Node succeeded"
                title="Node succeeded"
              >
                <i class="mdi mdi-check"></i>
              </span>
            `
            : isNodeExecutionFailed
              ? `
                <span
                  class="workflow-editor-node-execution-indicator is-failed"
                  aria-label="Node failed"
                  title="Node failed"
                >
                  <i class="mdi mdi-close"></i>
                </span>
              `
              : '';
        const auxiliaryPorts = node.kind === 'agent'
          ? `
            <span class="workflow-editor-node-auxiliary">
              ${AGENT_AUXILIARY_PORTS.map((port) => {
                const isCompatibleCandidate = compatibleAuxiliaryPort === port.id;
                const isActiveTargetPort =
                  connectionDraft?.hoveredTargetId === node.id && connectionDraft?.hoveredTargetPort === port.id;
                const connectedEdges = workflowDefinition.edges.filter(
                  (edge) => edge.target === node.id && edge.targetPort === port.id,
                );
                const connectionCount = connectedEdges.length;
                const connectedSourceNodes = connectedEdges
                  .map((edge) => getNode(edge.source))
                  .filter((candidate): candidate is WorkflowNode => Boolean(candidate));
                const primaryConnectedSourceNode = connectedSourceNodes[0];
                const primaryConnectedSourceDefinition = getNodeDefinition(primaryConnectedSourceNode);
                const connectedSourceTitle = primaryConnectedSourceNode
                  ? primaryConnectedSourceNode.label
                    || primaryConnectedSourceDefinition?.label
                    || primaryConnectedSourceNode.type
                  : null;
                const connectedProviderLabel = primaryConnectedSourceDefinition?.app_label
                  || primaryConnectedSourceDefinition?.label
                  || connectedSourceTitle;
                const connectedModelLabel = port.id === 'ai_languageModel'
                  ? getEffectiveModelLabel(primaryConnectedSourceNode, primaryConnectedSourceDefinition)
                  : '';
                const connectedModelStateLabel = connectedProviderLabel && connectedModelLabel
                  ? `${connectedProviderLabel} • ${connectedModelLabel}`
                  : connectedProviderLabel || connectedModelLabel || connectedSourceTitle;
                const actionIcon = connectionCount > 0 && port.id === 'ai_languageModel'
                  ? 'mdi-tune-variant'
                  : 'mdi-plus';
                const stateLabel = connectionCount > 0
                  ? port.id === 'ai_languageModel'
                    ? connectedModelStateLabel ?? 'Provider configured'
                    : `${connectionCount} tool${connectionCount === 1 ? '' : 's'} attached`
                  : port.id === 'ai_languageModel'
                    ? 'Choose a provider and model'
                    : 'No tools attached';
                const modelProviderAppId = port.id === 'ai_languageModel'
                  ? primaryConnectedSourceDefinition?.app_id ?? ''
                  : '';

                return `
                  <button
                    type="button"
                    class="workflow-editor-node-auxiliary-port${isCompatibleCandidate ? ' is-candidate' : ''}${isActiveTargetPort ? ' is-active' : ''}${connectionCount > 0 ? ' is-connected' : ''}${port.id === 'ai_languageModel' && connectionCount === 0 ? ' is-warning' : ''}"
                    data-workflow-node-aux-node="${escapeHtml(node.id)}"
                    data-workflow-node-aux-port="${port.id}"
                    ${modelProviderAppId ? `data-model-provider="${escapeHtml(modelProviderAppId)}"` : ''}
                    title="${escapeHtml(connectionCount > 0 && port.id === 'ai_languageModel' ? `${connectedModelStateLabel ?? port.label}` : `Add ${port.label}`)}"
                    aria-label="${escapeHtml(connectionCount > 0 && port.id === 'ai_languageModel' ? `${connectedModelStateLabel ?? port.label}` : `Add ${port.label}`)}"
                  >
                    <span class="workflow-editor-node-auxiliary-handle" aria-hidden="true"></span>
                    <span class="workflow-editor-node-auxiliary-label">
                      <span class="workflow-editor-node-auxiliary-text">${escapeHtml(port.label)}</span>
                      <span class="workflow-editor-node-auxiliary-state">${escapeHtml(stateLabel)}</span>
                    </span>
                      <span class="workflow-editor-node-auxiliary-action" aria-hidden="true">
                        <i class="mdi ${actionIcon}"></i>
                      </span>
                  </button>
                `;
              }).join('')}
            </span>
          `
          : '';
        const cardMarkup = node.kind === 'agent'
          ? `
            <span class="workflow-editor-node-card">
              <span class="workflow-editor-agent-panel">
                <span class="workflow-editor-agent-head">
                  <span class="workflow-editor-agent-brand">
                    <span class="workflow-editor-agent-icon">
                      <i class="mdi ${escapeHtml(icon)}"></i>
                    </span>
                  </span>
                  <span class="workflow-editor-agent-copy">
                    <span class="workflow-editor-agent-title">${escapeHtml(agentDisplayTitle)}</span>
                    ${showAgentKindLabel ? '<span class="workflow-editor-agent-kind">AI agent</span>' : ''}
                  </span>
                </span>
                <span class="workflow-editor-agent-divider" aria-hidden="true"></span>
                ${auxiliaryPorts}
              </span>
            </span>
          `
          : `
            <span class="workflow-editor-node-card">
              <span class="workflow-editor-node-icon">
                <i class="mdi ${escapeHtml(icon)}"></i>
              </span>
            </span>
          `;
        const copyMarkup = node.kind === 'agent'
          ? ''
          : `
            <span class="workflow-editor-node-copy">
              <span class="workflow-editor-node-title">${escapeHtml(title)}</span>
            </span>
          `;
        const nodeToolbarMarkup = isSelected
          ? `
            <div class="workflow-node-toolbar" data-node-toolbar="${escapeHtml(node.id)}">
              <button
                type="button"
                class="workflow-node-toolbar-button"
                data-node-action="run"
                data-node-action-id="${escapeHtml(node.id)}"
                aria-label="Run node"
                ${isExecutionPending ? 'disabled' : ''}
              >
                <i class="mdi ${isNodeExecutionPending ? 'mdi-loading mdi-spin' : 'mdi-play'}"></i>
              </button>
              <button
                type="button"
                class="workflow-node-toolbar-button"
                data-node-action="settings"
                data-node-action-id="${escapeHtml(node.id)}"
                aria-label="Open node settings"
              >
                <i class="mdi mdi-tune-variant"></i>
              </button>
              <button
                type="button"
                class="workflow-node-toolbar-button"
                data-node-action="delete"
                data-node-action-id="${escapeHtml(node.id)}"
                aria-label="Delete node"
              >
                <i class="mdi mdi-trash-can-outline"></i>
              </button>
            </div>
          `
          : '';

        return `
          <article
            class="workflow-editor-node workflow-editor-node--${escapeHtml(node.kind)}${isSelected ? ' is-selected' : ''}${isConnectionSource ? ' is-connection-source' : ''}${isConnectionCandidate ? ' is-connection-candidate' : ''}${isConnectionTarget ? ' is-connection-target' : ''}${agentNeedsModel ? ' is-agent-incomplete' : ''}${isNodeExecutionPending ? ' is-executing' : ''}${isNodeExecutionSucceeded ? ' is-execution-succeeded' : ''}${isNodeExecutionFailed ? ' is-execution-failed' : ''}"
            data-workflow-node-id="${escapeHtml(node.id)}"
            tabindex="0"
          >
            ${nodeToolbarMarkup}
            ${connectors}
            ${executionIndicatorMarkup}
            ${cardMarkup}
            ${copyMarkup}
          </article>
        `;
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

    const edgeMarkup = workflowDefinition.edges
      .map((edge) => {
        const sourceNode = getNode(edge.source);
        const targetNode = getNode(edge.target);
        if (!sourceNode || !targetNode) {
          return '';
        }

        const { sourcePoint, sourceSide, targetPoint, targetSide } = getEdgeAnchors(
          edge,
          sourceNode,
          targetNode,
        );
        const path = buildConnectionPath(sourcePoint, sourceSide, targetPoint, targetSide);
        const isHovered = hoveredEdgeId === edge.id;

        return `
          <g class="workflow-editor-edge" data-workflow-edge-id="${escapeHtml(edge.id)}">
            <path
              class="workflow-editor-edge-hit"
              data-workflow-edge-hit-id="${escapeHtml(edge.id)}"
              d="${path}"
            ></path>
            <path class="workflow-editor-edge-path${isHovered ? ' is-hovered' : ''}" d="${path}"></path>
          </g>
        `;
      })
      .join('');

    const draftMarkup = (() => {
      if (!connectionDraft) {
        return '';
      }

      const sourceNode = getNode(connectionDraft.sourceId);
      if (!sourceNode) {
        return '';
      }

      const targetPoint = connectionDraft.hoveredTargetId
        ? (() => {
            const hoveredNode = getNode(connectionDraft.hoveredTargetId);
            if (!hoveredNode) {
              return {
                x: connectionDraft.pointerX,
                y: connectionDraft.pointerY,
              };
            }

            if (connectionDraft.hoveredTargetPort) {
              return getAgentAuxiliaryPortPoint(hoveredNode, connectionDraft.hoveredTargetPort);
            }

            const targetSide =
              connectionDraft.hoveredTargetSide ??
              getPreferredConnectorSide(hoveredNode, getNodeCenter(sourceNode));

            return getConnectorPoint(hoveredNode, targetSide);
          })()
        : {
            x: connectionDraft.pointerX,
            y: connectionDraft.pointerY,
          };
      const sourceSide = getPreferredConnectorSide(sourceNode, targetPoint);
      const sourcePoint = getConnectorPoint(sourceNode, sourceSide);
      const targetSide = connectionDraft.hoveredTargetId
        ? connectionDraft.hoveredTargetPort
          ? 'top'
          : connectionDraft.hoveredTargetSide ?? getOppositeConnectorSide(sourceSide)
        : getOppositeConnectorSide(sourceSide);

      return `<path class="workflow-editor-edge-path workflow-editor-edge-path--draft" d="${buildConnectionPath(sourcePoint, sourceSide, targetPoint, targetSide)}"></path>`;
    })();

    canvas.edgeLayer.innerHTML = `${edgeMarkup}${draftMarkup}`;
  }

  function renderEdgeControls(): void {
    if (dragState || connectionDraft || !hoveredEdgeId) {
      canvas.edgeControls.innerHTML = '';
      return;
    }

    const hoveredEdge = workflowDefinition.edges.find((edge) => edge.id === hoveredEdgeId);
    if (!hoveredEdge) {
      canvas.edgeControls.innerHTML = '';
      return;
    }

    const sourceNode = getNode(hoveredEdge.source);
    const targetNode = getNode(hoveredEdge.target);
    if (!sourceNode || !targetNode) {
      canvas.edgeControls.innerHTML = '';
      return;
    }

    const { sourcePoint, sourceSide, targetPoint, targetSide } = getEdgeAnchors(
      hoveredEdge,
      sourceNode,
      targetNode,
    );
    const midpoint = getConnectionMidpoint(sourcePoint, sourceSide, targetPoint, targetSide);
    const controlPoint = viewportController.worldToScreen(midpoint);
    const controlX = clamp(Math.round(controlPoint.x), 20, Math.max(canvas.board.clientWidth - 20, 20));
    const controlY = clamp(Math.round(controlPoint.y), 20, Math.max(canvas.board.clientHeight - 20, 20));

    canvas.edgeControls.innerHTML = `
      <button
        type="button"
        class="workflow-editor-edge-remove"
        data-remove-edge="${escapeHtml(hoveredEdge.id)}"
        style="left: ${controlX}px; top: ${controlY}px;"
        aria-label="Remove connection"
      >
        <i class="mdi mdi-close"></i>
      </button>
    `;
  }

  function renderCanvas(): void {
    renderNodes();
    renderEdges();
    renderEdgeControls();
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
      settingChip.dataset.nodeSettingChipBinding
    ) {
      applyNodeSettingSuggestion(
        settingChip.dataset.nodeSettingChipKey,
        settingChip.dataset.nodeSettingChipValue,
        settingChip.dataset.nodeSettingChipBinding,
      );
      return;
    }

    if (target.closest('[data-workflow-run]')) {
      void executeDesignerRun(workflowRunUrl);
      return;
    }

    if (target.closest('[data-workflow-run-selected-node]')) {
      if (settingsNodeId) {
        void executeDesignerRun(getNodeRunUrl(settingsNodeId), { nodeId: settingsNodeId });
      }
      return;
    }

    if (target.closest('[data-workflow-fit-view]')) {
      repositionGraph();
      return;
    }

    if (target.closest('[data-workflow-zoom-in]')) {
      viewportController.zoomByStep('in');
      return;
    }

    if (target.closest('[data-workflow-zoom-out]')) {
      viewportController.zoomByStep('out');
      return;
    }

    const nodeAction = target.closest<HTMLElement>('[data-node-action]');
    if (nodeAction?.dataset.nodeAction && nodeAction.dataset.nodeActionId) {
      const nodeId = nodeAction.dataset.nodeActionId;
      const action = nodeAction.dataset.nodeAction;

      if (action === 'run') {
        openNodeSettings(nodeId);
        void executeDesignerRun(getNodeRunUrl(nodeId), { nodeId });
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
      if (isBrowserOpen) {
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

    if (contextMenuState && !target.closest('[data-workflow-node-menu]')) {
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
    if (nodeMenuAction?.dataset.nodeMenuAction && contextMenuState) {
      const nodeId = contextMenuState.nodeId;
      const action = nodeMenuAction.dataset.nodeMenuAction;
      closeNodeContextMenu();
      if (action === 'settings') {
        openNodeSettings(nodeId);
        return;
      }
      if (action === 'delete') {
        deleteNode(nodeId);
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

  canvas.board.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) {
      return;
    }

    const target = event.target as HTMLElement;
    if (
      target.closest('[data-workflow-node-id]') ||
      target.closest('[data-workflow-node-menu]') ||
      target.closest('[data-node-browser]') ||
      target.closest('[data-open-node-browser]') ||
      target.closest('[data-remove-edge]') ||
      target.closest('[data-workflow-settings-panel]')
    ) {
      return;
    }

    panState = {
      didMove: false,
      lastClientX: event.clientX,
      lastClientY: event.clientY,
      pointerId: event.pointerId,
    };
    canvas.board.classList.add('is-panning');
    canvas.board.setPointerCapture(event.pointerId);
  });

  canvas.nodeLayer.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) {
      return;
    }

    const target = event.target as HTMLElement;
    if (target.closest('[data-node-action]')) {
      return;
    }
    if (contextMenuState) {
      closeNodeContextMenu();
    }
    const auxiliaryPort = target.closest<HTMLElement>('[data-workflow-node-aux-port]');
    if (auxiliaryPort) {
      return;
    }

    const connector = target.closest<HTMLElement>('[data-workflow-node-connector]');
    if (connector?.dataset.workflowNodeConnector) {
      const connectorNode = getNode(connector.dataset.workflowNodeConnector);
      const connectorDefinition = getNodeDefinition(connectorNode);
      if (
        connectorNode
        && canNodeEmitConnections(connectorNode, workflowDefinition.edges, connectorDefinition)
      ) {
        beginConnection(
          connector.dataset.workflowNodeConnector,
          event.pointerId,
          event.clientX,
          event.clientY,
        );
        event.preventDefault();
        return;
      }
    }

    const nodeElement = target.closest<HTMLElement>('[data-workflow-node-id]');
    const nodeId = nodeElement?.dataset.workflowNodeId;
    if (!nodeElement || !nodeId) {
      return;
    }

    const node = workflowDefinition.nodes.find((item) => item.id === nodeId);
    if (!node) {
      return;
    }

    if (selectedNodeId !== nodeId) {
      selectedNodeId = nodeId;
      settingsNodeId = null;
      renderNodes();
      renderSettingsPanel();
    }

    if (settingsNodeId) {
      settingsNodeId = null;
      renderSettingsPanel();
    }

    const activeNodeElement = getNodeElement(canvas.nodeLayer, nodeId);
    if (!activeNodeElement) {
      return;
    }

    const cursorPoint = viewportController.screenToWorld(event.clientX, event.clientY);

    dragState = {
      nodeId,
      offsetX: cursorPoint.x - node.position.x,
      offsetY: cursorPoint.y - node.position.y,
      pointerId: event.pointerId,
    };

    activeNodeElement.classList.add('is-dragging');
    activeNodeElement.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  canvas.nodeLayer.addEventListener('contextmenu', (event) => {
    const target = event.target as HTMLElement;
    const nodeElement = target.closest<HTMLElement>('[data-workflow-node-id]');
    const nodeId = nodeElement?.dataset.workflowNodeId;
    if (!nodeId) {
      return;
    }

    event.preventDefault();
    openNodeContextMenu(nodeId, event.clientX, event.clientY);
  });

  canvas.board.addEventListener('pointermove', (event) => {
    if (dragState || connectionDraft) {
      if (hoveredEdgeId) {
        hoveredEdgeId = null;
        renderEdges();
        renderEdgeControls();
      }
      return;
    }

    const target = event.target as Element;
    const hoveredRemoveButton = target.closest<HTMLElement>('[data-remove-edge]');
    const hoveredEdgeHit = target.closest<SVGPathElement>('[data-workflow-edge-hit-id]');
    const nextHoveredEdgeId = hoveredRemoveButton?.dataset.removeEdge ?? hoveredEdgeHit?.dataset.workflowEdgeHitId ?? null;
    if (hoveredEdgeId === nextHoveredEdgeId) {
      return;
    }

    hoveredEdgeId = nextHoveredEdgeId;
    renderEdges();
    renderEdgeControls();
  });

  canvas.board.addEventListener('pointerleave', () => {
    if (!hoveredEdgeId) {
      return;
    }

    hoveredEdgeId = null;
    renderEdges();
    renderEdgeControls();
  });

  window.addEventListener('pointermove', (event) => {
    if (panState && event.pointerId === panState.pointerId) {
      const deltaX = event.clientX - panState.lastClientX;
      const deltaY = event.clientY - panState.lastClientY;
      if (Math.abs(deltaX) > 0 || Math.abs(deltaY) > 0) {
        panState.didMove = true;
        viewportController.panBy(deltaX, deltaY);
        panState.lastClientX = event.clientX;
        panState.lastClientY = event.clientY;
      }
      return;
    }

    if (connectionDraft && event.pointerId === connectionDraft.pointerId) {
      const pointerPoint = getPointFromClient(event.clientX, event.clientY);
      connectionDraft.pointerX = pointerPoint.x;
      connectionDraft.pointerY = pointerPoint.y;
      const nextHoveredTarget = getHoveredTarget(
        event.clientX,
        event.clientY,
        connectionDraft.sourceId,
      );
      const didHoverTargetChange =
        connectionDraft.hoveredTargetId !== nextHoveredTarget?.nodeId ||
        connectionDraft.hoveredTargetPort !== nextHoveredTarget?.targetPort ||
        connectionDraft.hoveredTargetSide !== nextHoveredTarget?.side;
      connectionDraft.hoveredTargetId = nextHoveredTarget?.nodeId ?? null;
      connectionDraft.hoveredTargetPort = nextHoveredTarget?.targetPort ?? null;
      connectionDraft.hoveredTargetSide = nextHoveredTarget?.side ?? null;
      renderNodes();
      if (didHoverTargetChange) {
        renderEdgeControls();
      }
      renderEdges();
      return;
    }

    if (!dragState || event.pointerId !== dragState.pointerId) {
      return;
    }

    const cursorPoint = viewportController.screenToWorld(event.clientX, event.clientY);

    updateNodePosition(dragState.nodeId, {
      x: cursorPoint.x - dragState.offsetX,
      y: cursorPoint.y - dragState.offsetY,
    });
  });

  function stopDragging(pointerId: number): void {
    if (!dragState || dragState.pointerId !== pointerId) {
      return;
    }

    const nodeElement = getNodeElement(canvas.nodeLayer, dragState.nodeId);
    if (nodeElement) {
      nodeElement.classList.remove('is-dragging');
      if (nodeElement.hasPointerCapture(pointerId)) {
        nodeElement.releasePointerCapture(pointerId);
      }
    }

    dragState = null;
    renderCanvas();
  }

  function stopPanning(pointerId: number): void {
    if (!panState || panState.pointerId !== pointerId) {
      return;
    }

    const didMove = panState.didMove;
    panState = null;
    canvas.board.classList.remove('is-panning');
    if (canvas.board.hasPointerCapture(pointerId)) {
      canvas.board.releasePointerCapture(pointerId);
    }

    if (!didMove) {
      if (selectedNodeId) {
        selectedNodeId = null;
        settingsNodeId = null;
        renderCanvas();
        renderSettingsPanel();
        return;
      }

      if (settingsNodeId) {
        settingsNodeId = null;
        renderSettingsPanel();
      }
    }
  }

  function stopConnecting(pointerId: number, clientX: number, clientY: number): void {
    if (!connectionDraft || connectionDraft.pointerId !== pointerId) {
      return;
    }

    const targetId = connectionDraft.hoveredTargetId;
    const targetPort = connectionDraft.hoveredTargetPort;
    const sourceId = connectionDraft.sourceId;
    connectionDraft = null;

    if (targetId && isValidConnection(sourceId, targetId, targetPort)) {
      addEdge(sourceId, targetId, targetPort ? { sourcePort: targetPort, targetPort } : undefined);
      return;
    }

    if (shouldOpenInsertBrowser(clientX, clientY)) {
      openInsertBrowser(sourceId, clientX, clientY);
      renderCanvas();
      return;
    }

    renderCanvas();
  }

  window.addEventListener('pointerup', (event) => {
    stopConnecting(event.pointerId, event.clientX, event.clientY);
    stopDragging(event.pointerId);
    stopPanning(event.pointerId);
  });

  window.addEventListener('pointercancel', (event) => {
    stopConnecting(event.pointerId, event.clientX, event.clientY);
    stopDragging(event.pointerId);
    stopPanning(event.pointerId);
  });

  canvas.board.addEventListener('wheel', (event) => {
    if (!event.ctrlKey && !event.metaKey) {
      return;
    }

    const zoomDelta = event.deltaY < 0 ? 0.08 : -0.08;
    viewportController.zoomAt(event.clientX, event.clientY, zoomDelta);
    event.preventDefault();
  }, { passive: false });

  root.addEventListener('keydown', (event) => {
    if (
      (event.key === 'Delete' || event.key === 'Backspace') &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.altKey &&
      selectedNodeId &&
      !isTextEntryTarget(event.target)
    ) {
      deleteNode(selectedNodeId);
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

    if (connectionDraft) {
      cancelConnection();
      return;
    }

    if (isBrowserOpen) {
      closeBrowser();
      return;
    }

    if (contextMenuState) {
      closeNodeContextMenu();
      return;
    }

    if (settingsNodeId) {
      closeNodeSettings();
    }
  });

  browser.searchInput.addEventListener('input', () => {
    searchQuery = browser.searchInput.value;
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

  syncDefinitionInput();
  renderCanvas();
  renderBrowser();
  renderSettingsPanel();
}
