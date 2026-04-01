import {
  CANVAS_EDGE_MARGIN,
  NODE_CARD_HEIGHT,
  NODE_CARD_WIDTH,
  NODE_COLUMN_GAP,
  NODE_HEIGHT,
  NODE_ROW_GAP,
  NODE_WIDTH,
  SURFACE_PADDING,
} from './workflowDesigner/constants';
import { buildNodeRegistry, getAvailablePaletteSections } from './workflowDesigner/registry/nodeRegistry';
import { normalizeWorkflowDefinition, serializeWorkflowDefinition } from './workflowDesigner/schema/workflowSchema';
import type {
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeTemplateField,
  WorkflowNodeTemplate,
  WorkflowPaletteSection,
  WorkflowPersistedDefinition,
} from './workflowDesigner/types';
import {
  clamp,
  cloneValue,
  createId,
  escapeHtml,
  formatKindLabel,
  getTemplateFieldOptions,
  getTemplateFieldValue,
  isTemplateFieldVisible,
  parseJsonScript,
} from './workflowDesigner/utils';

type BrowserElements = {
  browser: HTMLElement;
  browserContent: HTMLElement;
  browserDescription: HTMLElement;
  browserEmpty: HTMLElement;
  browserTitle: HTMLElement;
  openButton: HTMLButtonElement;
  searchInput: HTMLInputElement;
};

type CanvasElements = {
  board: HTMLElement;
  definitionInput: HTMLInputElement | HTMLTextAreaElement;
  edgeControls: HTMLElement;
  edgeLayer: SVGSVGElement;
  emptyState: HTMLElement;
  nodeLayer: HTMLElement;
  nodeMenu: HTMLElement;
  settingsDescription: HTMLElement;
  settingsFields: HTMLElement;
  settingsPanel: HTMLElement;
  settingsTitle: HTMLElement;
};

type ConnectorSide = 'top' | 'right' | 'bottom' | 'left';
type AgentAuxiliaryPortId = 'ai_languageModel' | 'ai_tool';
type BrowserMode = 'default' | 'starter';

type DragState = {
  nodeId: string;
  offsetX: number;
  offsetY: number;
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

type Point = {
  x: number;
  y: number;
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
const AGENT_NODE_WIDTH = 224;
const AGENT_NODE_HEIGHT = 164;
const AGENT_NODE_CARD_WIDTH = 224;
const AGENT_NODE_CARD_HEIGHT = 164;
const AGENT_AUXILIARY_PORT_ANCHOR_X = 18;
const AGENT_AUXILIARY_PORT_ANCHOR_Y = 102;
const AGENT_AUXILIARY_PORT_ROW_GAP = 34;
const NODE_CONTEXT_MENU_WIDTH = 224;
const NODE_CONTEXT_MENU_HEIGHT = 142;
const NODE_CONTEXT_MENU_MARGIN = 12;
const NODE_CONTEXT_MENU_OFFSET_X = 10;
const NODE_CONTEXT_MENU_OFFSET_Y = 6;
const AGENT_LANGUAGE_MODEL_NODE_TYPES = new Set<string>(['tool.openai_chat_model']);

function isAgentLanguageModelNodeType(nodeType: string | null | undefined): boolean {
  return Boolean(nodeType && AGENT_LANGUAGE_MODEL_NODE_TYPES.has(nodeType));
}

function isAgentToolCompatibleNode(definition: Pick<WorkflowNodeDefinition, 'kind' | 'type'>): boolean {
  return definition.kind === 'tool' && !isAgentLanguageModelNodeType(definition.type);
}

function getBrowserElements(root: ParentNode): BrowserElements | null {
  const browser = root.querySelector<HTMLElement>('[data-node-browser]');
  const browserContent = root.querySelector<HTMLElement>('[data-node-browser-content]');
  const browserDescription = root.querySelector<HTMLElement>('[data-node-browser-description]');
  const browserEmpty = root.querySelector<HTMLElement>('[data-node-browser-empty]');
  const browserTitle = root.querySelector<HTMLElement>('[data-node-browser-title]');
  const openButton = root.querySelector<HTMLButtonElement>('[data-open-node-browser]');
  const searchInput = root.querySelector<HTMLInputElement>('[data-node-browser-search]');

  if (
    !browser ||
    !browserContent ||
    !browserDescription ||
    !browserEmpty ||
    !browserTitle ||
    !openButton ||
    !searchInput
  ) {
    return null;
  }

  return {
    browser,
    browserContent,
    browserDescription,
    browserEmpty,
    browserTitle,
    openButton,
    searchInput,
  };
}

function getCanvasElements(root: ParentNode): CanvasElements | null {
  const board = root.querySelector<HTMLElement>('[data-workflow-board]');
  const definitionInput = root.querySelector<HTMLInputElement | HTMLTextAreaElement>('#id_definition');
  const edgeControls = root.querySelector<HTMLElement>('[data-workflow-edge-controls]');
  const edgeLayer = root.querySelector<SVGSVGElement>('[data-workflow-edge-layer]');
  const emptyState = root.querySelector<HTMLElement>('[data-workflow-empty-state]');
  const nodeLayer = root.querySelector<HTMLElement>('[data-workflow-node-layer]');
  const nodeMenu = root.querySelector<HTMLElement>('[data-workflow-node-menu]');
  const settingsDescription = root.querySelector<HTMLElement>('[data-workflow-settings-description]');
  const settingsFields = root.querySelector<HTMLElement>('[data-workflow-settings-fields]');
  const settingsPanel = root.querySelector<HTMLElement>('[data-workflow-settings-panel]');
  const settingsTitle = root.querySelector<HTMLElement>('[data-workflow-settings-title]');

  if (
    !board ||
    !definitionInput ||
    !edgeControls ||
    !edgeLayer ||
    !emptyState ||
    !nodeLayer ||
    !nodeMenu ||
    !settingsDescription ||
    !settingsFields ||
    !settingsPanel ||
    !settingsTitle
  ) {
    return null;
  }

  return {
    board,
    definitionInput,
    edgeControls,
    edgeLayer,
    emptyState,
    nodeLayer,
    nodeMenu,
    settingsDescription,
    settingsFields,
    settingsPanel,
    settingsTitle,
  };
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

function filterNodeDefinitions(
  definitions: WorkflowNodeDefinition[],
  query: string,
): WorkflowNodeDefinition[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return definitions;
  }

  return definitions.filter((definition) => {
    const haystack = [
      definition.label,
      definition.description,
      definition.type,
      definition.kind,
      definition.app_label ?? '',
    ]
      .join(' ')
      .toLowerCase();

    return haystack.includes(normalizedQuery);
  });
}

function renderPaletteDefinitions(
  definitions: WorkflowNodeDefinition[],
  mode: BrowserMode,
): string {
  return definitions
    .map((definition) => {
      const icon = definition.icon ?? 'mdi-vector-square';
      const meta = definition.app_label && definition.app_label !== definition.label
        ? definition.app_label
        : formatKindLabel(definition.kind) || definition.kind;

      return `
        <button
          type="button"
          class="workflow-node-browser-item${mode === 'starter' ? ' workflow-node-browser-item--starter' : ''}"
          data-node-browser-item="${escapeHtml(definition.type)}"
          aria-label="${escapeHtml(definition.label)}"
        >
          <span class="workflow-node-browser-item-icon">
            <i class="mdi ${escapeHtml(icon)}"></i>
          </span>
          <span class="workflow-node-browser-item-copy">
            <span class="workflow-node-browser-item-title">${escapeHtml(definition.label)}</span>
            <span class="workflow-node-browser-item-description">${escapeHtml(definition.description)}</span>
            <span class="workflow-node-browser-item-meta">${escapeHtml(meta)}</span>
          </span>
        </button>
      `;
    })
    .join('');
}

function renderPaletteSections(sections: WorkflowPaletteSection[], query: string): string {
  const filteredSections = sections
    .map((section) => ({
      ...section,
      definitions: filterNodeDefinitions(section.definitions, query),
    }))
    .filter((section) => section.definitions.length > 0);

  return filteredSections
    .map((section) => `
      <section class="workflow-node-browser-section">
        <div class="workflow-node-browser-section-title">${escapeHtml(section.label)}</div>
        <div class="workflow-node-browser-grid">
          ${renderPaletteDefinitions(section.definitions, 'default')}
        </div>
      </section>
    `)
    .join('');
}

function getBoardBounds(
  board: HTMLElement,
  nodeHeight = NODE_HEIGHT,
  nodeWidth = NODE_WIDTH,
): { maxX: number; maxY: number } {
  const boardWidth = Math.max(board.clientWidth, nodeWidth + CANVAS_EDGE_MARGIN * 2);
  const boardHeight = Math.max(board.clientHeight, nodeHeight + CANVAS_EDGE_MARGIN * 2);

  return {
    maxX: Math.max(CANVAS_EDGE_MARGIN, boardWidth - nodeWidth - CANVAS_EDGE_MARGIN),
    maxY: Math.max(CANVAS_EDGE_MARGIN, boardHeight - nodeHeight - CANVAS_EDGE_MARGIN),
  };
}

function clampNodePosition(
  board: HTMLElement,
  position: { x: number; y: number },
  nodeHeight = NODE_HEIGHT,
  nodeWidth = NODE_WIDTH,
): { x: number; y: number } {
  const bounds = getBoardBounds(board, nodeHeight, nodeWidth);

  return {
    x: clamp(Math.round(position.x), CANVAS_EDGE_MARGIN, bounds.maxX),
    y: clamp(Math.round(position.y), CANVAS_EDGE_MARGIN, bounds.maxY),
  };
}

function nodesOverlap(
  first: { x: number; y: number },
  second: { x: number; y: number },
  firstHeight = NODE_HEIGHT,
  secondHeight = NODE_HEIGHT,
  firstWidth = NODE_WIDTH,
  secondWidth = NODE_WIDTH,
  padding = 28,
): boolean {
  return !(
    first.x + firstWidth + padding <= second.x ||
    second.x + secondWidth + padding <= first.x ||
    first.y + firstHeight + padding <= second.y ||
    second.y + secondHeight + padding <= first.y
  );
}

function hasNodeCollision(
  definition: WorkflowDefinition,
  position: { x: number; y: number },
  nodeHeight = NODE_HEIGHT,
  nodeWidth = NODE_WIDTH,
  ignoreNodeId?: string,
): boolean {
  return definition.nodes.some(
    (node) =>
      node.id !== ignoreNodeId &&
      nodesOverlap(
        position,
        node.position,
        nodeHeight,
        getNodeRenderHeight(node),
        nodeWidth,
        getNodeRenderWidth(node),
      ),
  );
}

function getSuggestedNodePosition(
  board: HTMLElement,
  definition: WorkflowDefinition,
  selectedNodeId: string | null,
  nextNode: Pick<WorkflowNode, 'kind'> | null | undefined,
): { x: number; y: number } {
  const nextNodeHeight = getNodeRenderHeight(nextNode);
  const nextNodeWidth = getNodeRenderWidth(nextNode);
  const selectedNode = selectedNodeId
    ? definition.nodes.find((node) => node.id === selectedNodeId)
    : undefined;
  if (selectedNode) {
    const nextPosition = [
      {
        x: selectedNode.position.x + NODE_COLUMN_GAP,
        y: selectedNode.position.y,
      },
      {
        x: selectedNode.position.x,
        y: selectedNode.position.y + NODE_ROW_GAP,
      },
      {
        x: selectedNode.position.x - NODE_COLUMN_GAP,
        y: selectedNode.position.y,
      },
      {
        x: selectedNode.position.x,
        y: selectedNode.position.y - NODE_ROW_GAP,
      },
    ]
      .map((position) => clampNodePosition(board, position, nextNodeHeight, nextNodeWidth))
      .find((position) => !hasNodeCollision(definition, position, nextNodeHeight, nextNodeWidth));

    if (nextPosition) {
      return nextPosition;
    }

    return clampNodePosition(board, {
      x: selectedNode.position.x + NODE_COLUMN_GAP,
      y: selectedNode.position.y,
    }, nextNodeHeight, nextNodeWidth);
  }

  if (definition.nodes.length === 0) {
    return clampNodePosition(board, {
      x: board.clientWidth / 2 - nextNodeWidth / 2,
      y: 132,
    }, nextNodeHeight, nextNodeWidth);
  }

  const lastNode = definition.nodes[definition.nodes.length - 1];
  const bounds = getBoardBounds(board, nextNodeHeight, nextNodeWidth);
  const nextX = lastNode.position.x + getNodeRenderWidth(lastNode) + 24;
  const nextY = lastNode.position.y + 24;

  if (nextX > bounds.maxX) {
    return clampNodePosition(board, {
      x: SURFACE_PADDING,
      y: lastNode.position.y + NODE_ROW_GAP,
    }, nextNodeHeight, nextNodeWidth);
  }

  return clampNodePosition(board, {
    x: nextX,
    y: nextY,
  }, nextNodeHeight, nextNodeWidth);
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

function canNodeReceiveConnections(node: WorkflowNode): boolean {
  return node.kind !== 'trigger';
}

function canNodeEmitConnections(node: WorkflowNode): boolean {
  return node.kind !== 'response';
}

function getNodeRenderWidth(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return node?.kind === 'agent' ? AGENT_NODE_WIDTH : NODE_WIDTH;
}

function getNodeRenderHeight(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return node?.kind === 'agent' ? AGENT_NODE_HEIGHT : NODE_HEIGHT;
}

function getNodeCardWidth(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return node?.kind === 'agent' ? AGENT_NODE_CARD_WIDTH : NODE_CARD_WIDTH;
}

function getNodeCardHeight(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return node?.kind === 'agent' ? AGENT_NODE_CARD_HEIGHT : NODE_CARD_HEIGHT;
}

function getCompatibleAgentAuxiliaryPort(
  sourceNode: WorkflowNode | undefined,
  targetNode: WorkflowNode | undefined,
): AgentAuxiliaryPortId | null {
  if (!sourceNode || !targetNode || targetNode.kind !== 'agent') {
    return null;
  }

  if (isAgentLanguageModelNodeType(sourceNode.type)) {
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
        ? isAgentLanguageModelNodeType(definition.type)
        : isAgentToolCompatibleNode(definition),
    )
    .map((definition) => definition.type);
}

function getNodeCardOffsetX(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return (getNodeRenderWidth(node) - getNodeCardWidth(node)) / 2;
}

function getNodeCenter(node: WorkflowNode): Point {
  return {
    x: node.position.x + getNodeCardOffsetX(node) + getNodeCardWidth(node) / 2,
    y: node.position.y + getNodeCardHeight(node) / 2,
  };
}

function getConnectorPoint(node: WorkflowNode, side: ConnectorSide): Point {
  const cardOffsetX = getNodeCardOffsetX(node);
  const cardWidth = getNodeCardWidth(node);
  const cardHeight = getNodeCardHeight(node);

  switch (side) {
    case 'top':
      return {
        x: node.position.x + cardOffsetX + cardWidth / 2,
        y: node.position.y,
      };
    case 'right':
      return {
        x: node.position.x + cardOffsetX + cardWidth,
        y: node.position.y + cardHeight / 2,
      };
    case 'bottom':
      return {
        x: node.position.x + cardOffsetX + cardWidth / 2,
        y: node.position.y + cardHeight,
      };
    case 'left':
    default:
      return {
        x: node.position.x + cardOffsetX,
        y: node.position.y + cardHeight / 2,
      };
  }
}

function getAgentAuxiliaryPortPoint(node: WorkflowNode, portId: AgentAuxiliaryPortId): Point {
  const portIndex = AGENT_AUXILIARY_PORTS.findIndex((port) => port.id === portId);

  return {
    x: node.position.x + AGENT_AUXILIARY_PORT_ANCHOR_X,
    y: node.position.y + AGENT_AUXILIARY_PORT_ANCHOR_Y + portIndex * AGENT_AUXILIARY_PORT_ROW_GAP,
  };
}

function getConnectorVector(side: ConnectorSide): Point {
  switch (side) {
    case 'top':
      return { x: 0, y: -1 };
    case 'right':
      return { x: 1, y: 0 };
    case 'bottom':
      return { x: 0, y: 1 };
    case 'left':
    default:
      return { x: -1, y: 0 };
  }
}

function getOppositeConnectorSide(side: ConnectorSide): ConnectorSide {
  switch (side) {
    case 'top':
      return 'bottom';
    case 'right':
      return 'left';
    case 'bottom':
      return 'top';
    case 'left':
    default:
      return 'right';
  }
}

function getPreferredConnectorSide(node: WorkflowNode, point: Point): ConnectorSide {
  const center = getNodeCenter(node);
  const deltaX = point.x - center.x;
  const deltaY = point.y - center.y;

  if (Math.abs(deltaX) >= Math.abs(deltaY)) {
    return deltaX >= 0 ? 'right' : 'left';
  }

  return deltaY >= 0 ? 'bottom' : 'top';
}

function getConnectionSides(
  sourceNode: WorkflowNode,
  targetNode: WorkflowNode,
): { sourceSide: ConnectorSide; targetSide: ConnectorSide } {
  return {
    sourceSide: getPreferredConnectorSide(sourceNode, getNodeCenter(targetNode)),
    targetSide: getPreferredConnectorSide(targetNode, getNodeCenter(sourceNode)),
  };
}

function buildConnectionPath(
  source: Point,
  sourceSide: ConnectorSide,
  target: Point,
  targetSide: ConnectorSide,
): string {
  const controlOffset = getConnectionControlOffset(source, target);
  const sourceVector = getConnectorVector(sourceSide);
  const targetVector = getConnectorVector(targetSide);
  const sourceControl = {
    x: source.x + sourceVector.x * controlOffset,
    y: source.y + sourceVector.y * controlOffset,
  };
  const targetControl = {
    x: target.x + targetVector.x * controlOffset,
    y: target.y + targetVector.y * controlOffset,
  };

  return `M ${source.x} ${source.y} C ${sourceControl.x} ${sourceControl.y}, ${targetControl.x} ${targetControl.y}, ${target.x} ${target.y}`;
}

function getConnectionControlOffset(
  source: Point,
  target: Point,
): number {
  return Math.max(Math.max(Math.abs(target.x - source.x), Math.abs(target.y - source.y)) * 0.4, 64);
}

function getConnectionMidpoint(
  source: Point,
  sourceSide: ConnectorSide,
  target: Point,
  targetSide: ConnectorSide,
): { x: number; y: number } {
  const controlOffset = getConnectionControlOffset(source, target);
  const sourceVector = getConnectorVector(sourceSide);
  const targetVector = getConnectorVector(targetSide);
  const startControl = {
    x: source.x + sourceVector.x * controlOffset,
    y: source.y + sourceVector.y * controlOffset,
  };
  const endControl = {
    x: target.x + targetVector.x * controlOffset,
    y: target.y + targetVector.y * controlOffset,
  };
  const t = 0.5;
  const mt = 1 - t;

  return {
    x:
      mt ** 3 * source.x +
      3 * mt ** 2 * t * startControl.x +
      3 * mt * t ** 2 * endControl.x +
      t ** 3 * target.x,
    y:
      mt ** 3 * source.y +
      3 * mt ** 2 * t * startControl.y +
      3 * mt * t ** 2 * endControl.y +
      t ** 3 * target.y,
  };
}

function getEdgeAnchors(
  edge: WorkflowDefinition['edges'][number],
  sourceNode: WorkflowNode,
  targetNode: WorkflowNode,
): {
  sourcePoint: Point;
  sourceSide: ConnectorSide;
  targetPoint: Point;
  targetSide: ConnectorSide;
} {
  if (edge.targetPort === 'ai_languageModel' || edge.targetPort === 'ai_tool') {
    const targetPoint = getAgentAuxiliaryPortPoint(targetNode, edge.targetPort);
    const sourceSide = getPreferredConnectorSide(sourceNode, targetPoint);

    return {
      sourcePoint: getConnectorPoint(sourceNode, sourceSide),
      sourceSide,
      targetPoint,
      targetSide: 'top',
    };
  }

  const { sourceSide, targetSide } = getConnectionSides(sourceNode, targetNode);
  return {
    sourcePoint: getConnectorPoint(sourceNode, sourceSide),
    sourceSide,
    targetPoint: getConnectorPoint(targetNode, targetSide),
    targetSide,
  };
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

  const fallbackDefinition = parseJsonScript<WorkflowPersistedDefinition>('workflow-definition-data', {
    edges: [],
    nodes: [],
  });
  const persistedDefinition = parsePersistedDefinition(canvas.definitionInput) ?? fallbackDefinition;
  const workflowDefinition = normalizeWorkflowDefinition(persistedDefinition);
  const nodeTemplates = parseJsonScript<WorkflowNodeTemplate[]>('workflow-node-templates-data', []);
  const nodeRegistry = buildNodeRegistry(nodeTemplates);

  let isBrowserOpen = workflowDefinition.nodes.length === 0;
  let searchQuery = '';
  let selectedNodeId: string | null = null;
  let settingsNodeId: string | null = null;
  let dragState: DragState | null = null;
  let connectionDraft: ConnectionDraft | null = null;
  let contextMenuState: ContextMenuState | null = null;
  let hoveredEdgeId: string | null = null;
  let insertDraft: InsertDraft | null = null;

  function syncDefinitionInput(): void {
    canvas.definitionInput.value = JSON.stringify(serializeWorkflowDefinition(workflowDefinition));
  }

  function getNode(nodeId: string | null): WorkflowNode | undefined {
    if (!nodeId) {
      return undefined;
    }

    return workflowDefinition.nodes.find((node) => node.id === nodeId);
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

    const compatibleAuxiliaryPort = getCompatibleAgentAuxiliaryPort(sourceNode, targetNode);
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

    if (!canNodeEmitConnections(sourceNode) || !canNodeReceiveConnections(targetNode)) {
      return false;
    }

    return !hasConnection(sourceId, targetId, null);
  }

  function getPointFromClient(clientX: number, clientY: number): Point {
    const boardRect = canvas.board.getBoundingClientRect();

    return {
      x: clientX - boardRect.left + canvas.board.scrollLeft,
      y: clientY - boardRect.top + canvas.board.scrollTop,
    };
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

    workflowDefinition.edges = workflowDefinition.edges.filter((edge) => edge.source !== node.id);
    configuredTargetIds.forEach((targetId) => {
      workflowDefinition.edges.push({
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

  function renderSettingsPanel(): void {
    const settingsNode = getNode(settingsNodeId);
    const nodeDefinition = getNodeDefinition(settingsNode);
    if (!settingsNode || !nodeDefinition) {
      canvas.settingsPanel.hidden = true;
      canvas.settingsFields.innerHTML = '';
      return;
    }

    const visibleFields = nodeDefinition.fields.filter((field) => isTemplateFieldVisible(settingsNode, field));
    const fieldMarkup = visibleFields
      .map((field) => {
        const fieldId = `workflow-node-setting-${settingsNode.id}-${field.key}`;
        const value = getTemplateFieldValue(settingsNode, field);
        const helpText = field.help_text
          ? `<div class="workflow-editor-settings-help">${escapeHtml(field.help_text)}</div>`
          : '';

        if (field.type === 'textarea') {
          return `
            <div class="workflow-editor-settings-group">
              <label class="form-label" for="${escapeHtml(fieldId)}">${escapeHtml(field.label)}</label>
              <textarea
                id="${escapeHtml(fieldId)}"
                class="form-control workflow-editor-settings-control"
                rows="${field.rows ?? 4}"
                data-node-setting-key="${escapeHtml(field.key)}"
                data-node-setting-type="${escapeHtml(field.type)}"
              >${escapeHtml(value)}</textarea>
              ${helpText}
            </div>
          `;
        }

        if (field.type === 'select' || field.type === 'node_target') {
          const options = (field.type === 'node_target'
            ? getNodeTargetOptions(settingsNode, workflowDefinition)
            : getTemplateFieldOptions(settingsNode, field)
          )
            .map(
              (option) => `
                <option value="${escapeHtml(option.value)}"${option.value === value ? ' selected' : ''}>
                  ${escapeHtml(option.label)}
                </option>
              `,
            )
            .join('');

          return `
            <div class="workflow-editor-settings-group">
              <label class="form-label" for="${escapeHtml(fieldId)}">${escapeHtml(field.label)}</label>
              <select
                id="${escapeHtml(fieldId)}"
                class="form-select workflow-editor-settings-control"
                data-node-setting-key="${escapeHtml(field.key)}"
                data-node-setting-type="${escapeHtml(field.type)}"
              >
                <option value="">Select</option>
                ${options}
              </select>
              ${helpText}
            </div>
          `;
        }

        return `
          <div class="workflow-editor-settings-group">
            <label class="form-label" for="${escapeHtml(fieldId)}">${escapeHtml(field.label)}</label>
            <input
              id="${escapeHtml(fieldId)}"
              type="text"
              class="form-control workflow-editor-settings-control"
              value="${escapeHtml(value)}"
              placeholder="${escapeHtml(field.placeholder ?? '')}"
              data-node-setting-key="${escapeHtml(field.key)}"
              data-node-setting-type="${escapeHtml(field.type)}"
            >
            ${helpText}
          </div>
        `;
      })
      .join('');

    const description = nodeDefinition.description || nodeDefinition.label;
    canvas.settingsPanel.hidden = false;
    canvas.settingsTitle.textContent = settingsNode.label || nodeDefinition.label;
    canvas.settingsDescription.textContent = description;
    canvas.settingsFields.innerHTML = `
      <div class="workflow-editor-settings-group">
        <label class="form-label" for="workflow-node-label-${escapeHtml(settingsNode.id)}">Node name</label>
        <input
          id="workflow-node-label-${escapeHtml(settingsNode.id)}"
          type="text"
          class="form-control workflow-editor-settings-control"
          value="${escapeHtml(settingsNode.label)}"
          data-node-setting-label
        >
      </div>
      ${fieldMarkup || '<div class="workflow-editor-settings-empty">No editable settings for this node yet.</div>'}
    `;
  }

  function getNodeContextMenuPosition(clientX: number, clientY: number): { x: number; y: number } {
    const boardRect = canvas.board.getBoundingClientRect();
    const rawX = clientX - boardRect.left + canvas.board.scrollLeft + NODE_CONTEXT_MENU_OFFSET_X;
    const rawY = clientY - boardRect.top + canvas.board.scrollTop + NODE_CONTEXT_MENU_OFFSET_Y;
    const minX = canvas.board.scrollLeft + NODE_CONTEXT_MENU_MARGIN;
    const minY = canvas.board.scrollTop + NODE_CONTEXT_MENU_MARGIN;
    const maxX = Math.max(
      minX,
      canvas.board.scrollLeft + canvas.board.clientWidth - NODE_CONTEXT_MENU_WIDTH - NODE_CONTEXT_MENU_MARGIN,
    );
    const maxY = Math.max(
      minY,
      canvas.board.scrollTop + canvas.board.clientHeight - NODE_CONTEXT_MENU_HEIGHT - NODE_CONTEXT_MENU_MARGIN,
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
      nodeDefinition?.app_label && nodeDefinition.app_label !== 'Workflow'
        ? nodeDefinition.app_label
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

  function renderBrowser(): void {
    const emptyWorkflow = isEmptyWorkflow();
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
    let title = 'Add node';
    let description = insertDraft
      ? 'Choose the next step to connect from here.'
      : 'Choose the next step to add to this workflow.';
    let emptyMessage = 'No matching nodes';
    let markup = renderPaletteSections(filteredSections, searchQuery);

    if (emptyWorkflow) {
      const triggerDefinitions = filterNodeDefinitions(
        nodeRegistry.definitions.filter((definition) => definition.kind === 'trigger'),
        searchQuery,
      );
      title = 'What triggers this workflow?';
      description = 'A trigger is the first step that decides how your workflow starts.';
      emptyMessage = 'No matching triggers';
      markup = triggerDefinitions.length > 0
        ? `<div class="workflow-node-browser-list">${renderPaletteDefinitions(triggerDefinitions, 'starter')}</div>`
        : '';
    } else if (insertPort) {
      title = insertPort.id === 'ai_languageModel' ? 'Attach model provider' : 'Attach tool';
      description = insertPort.id === 'ai_languageModel'
        ? 'Choose a provider-specific model node to attach to this agent.'
        : 'Choose any tool or integration node to attach to this agent.';
      emptyMessage = insertPort.id === 'ai_languageModel'
        ? 'No matching model providers'
        : 'No matching tools';
    }

    browser.browser.hidden = !isBrowserOpen;
    browser.browser.classList.toggle('is-starter-mode', emptyWorkflow);
    browser.browserTitle.textContent = title;
    browser.browserDescription.textContent = description;
    browser.browserDescription.hidden = description.length === 0;
    browser.openButton.classList.toggle('is-active', isBrowserOpen);
    browser.openButton.hidden = emptyWorkflow;
    browser.searchInput.placeholder = 'Search nodes...';
    browser.browserContent.innerHTML = markup;
    browser.browserEmpty.textContent = emptyMessage;
    browser.browserEmpty.hidden = markup.length > 0;
  }

  function renderEmptyState(): void {
    const emptyWorkflow = isEmptyWorkflow();
    canvas.board.classList.toggle('is-empty-workflow', emptyWorkflow);
    canvas.emptyState.hidden = !emptyWorkflow;
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
        const isConnectionSource = connectionDraft?.sourceId === node.id;
        const isConnectionCandidate = connectionDraft
          ? isValidConnection(connectionDraft.sourceId, node.id)
          : false;
        const isConnectionTarget = connectionDraft?.hoveredTargetId === node.id;
        const sourceConnectionNode = connectionDraft ? getNode(connectionDraft.sourceId) : undefined;
        const compatibleAuxiliaryPort = connectionDraft
          ? getCompatibleAgentAuxiliaryPort(sourceConnectionNode, node)
          : null;
        const canReceiveConnections = canNodeReceiveConnections(node);
        const canEmitConnections = canNodeEmitConnections(node);
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
        const connectedModelNode = modelConnections
          .map((edge) => getNode(edge.source))
          .find((candidate): candidate is WorkflowNode => Boolean(candidate));
        const connectedModelTitle = connectedModelNode
          ? connectedModelNode.label || getNodeDefinition(connectedModelNode)?.label || connectedModelNode.type
          : null;
        const agentNeedsModel = node.kind === 'agent' && modelConnections.length === 0;
        const connectors = (canReceiveConnections || canEmitConnections)
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
                const connectedSourceTitle = primaryConnectedSourceNode
                  ? primaryConnectedSourceNode.label
                    || getNodeDefinition(primaryConnectedSourceNode)?.label
                    || primaryConnectedSourceNode.type
                  : null;
                const actionIcon = connectionCount > 0 && port.id === 'ai_languageModel'
                  ? 'mdi-chevron-right'
                  : 'mdi-plus';
                const stateLabel = connectionCount > 0
                  ? port.id === 'ai_languageModel'
                    ? connectedSourceTitle ?? 'Provider attached'
                    : `${connectionCount} tool${connectionCount === 1 ? '' : 's'} attached`
                  : port.id === 'ai_languageModel'
                    ? 'No provider attached'
                    : 'No tools attached';

                return `
                  <button
                    type="button"
                    class="workflow-editor-node-auxiliary-port${isCompatibleCandidate ? ' is-candidate' : ''}${isActiveTargetPort ? ' is-active' : ''}${connectionCount > 0 ? ' is-connected' : ''}${port.id === 'ai_languageModel' && connectionCount === 0 ? ' is-warning' : ''}"
                    data-workflow-node-aux-node="${escapeHtml(node.id)}"
                    data-workflow-node-aux-port="${port.id}"
                    title="${escapeHtml(connectionCount > 0 && port.id === 'ai_languageModel' ? `Open ${port.label}` : `Add ${port.label}`)}"
                    aria-label="${escapeHtml(connectionCount > 0 && port.id === 'ai_languageModel' ? `Open ${port.label}` : `Add ${port.label}`)}"
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

        return `
          <article
            class="workflow-editor-node workflow-editor-node--${escapeHtml(node.kind)}${isSelected ? ' is-selected' : ''}${isConnectionSource ? ' is-connection-source' : ''}${isConnectionCandidate ? ' is-connection-candidate' : ''}${isConnectionTarget ? ' is-connection-target' : ''}${agentNeedsModel ? ' is-agent-incomplete' : ''}"
            data-workflow-node-id="${escapeHtml(node.id)}"
            tabindex="0"
          >
            ${connectors}
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
    const controlX = clamp(Math.round(midpoint.x), 20, Math.max(canvas.board.clientWidth - 20, 20));
    const controlY = clamp(Math.round(midpoint.y), 20, Math.max(canvas.board.clientHeight - 20, 20));

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
    renderNodeContextMenu();
  }

  function closeBrowser(): void {
    isBrowserOpen = false;
    insertDraft = null;
    contextMenuState = null;
    renderBrowser();
    renderNodeContextMenu();
  }

  function cancelConnection(): void {
    connectionDraft = null;
    renderCanvas();
  }

  function openBrowser(): void {
    isBrowserOpen = true;
    contextMenuState = null;
    renderBrowser();
    renderNodeContextMenu();
    window.setTimeout(() => {
      browser.searchInput.focus();
    }, 0);
  }

  function openInsertBrowser(sourceId: string, clientX: number, clientY: number): void {
    const boardRect = canvas.board.getBoundingClientRect();
    insertDraft = {
      position: clampNodePosition(canvas.board, {
        x: clientX - boardRect.left + canvas.board.scrollLeft - NODE_WIDTH / 2,
        y: clientY - boardRect.top + canvas.board.scrollTop - NODE_HEIGHT / 2,
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
    workflowDefinition.nodes.push(newNode);
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

  function updateSelectedNodeLabel(value: string): void {
    const settingsNode = getNode(settingsNodeId);
    if (!settingsNode) {
      return;
    }

    settingsNode.label = value;
    syncDefinitionInput();
    renderCanvas();
    renderSettingsPanel();
  }

  function updateSelectedNodeField(key: string, value: string): void {
    const settingsNode = getNode(settingsNodeId);
    if (!settingsNode) {
      return;
    }

    const nextConfig = { ...(settingsNode.config ?? {}) };
    if (value === '') {
      delete nextConfig[key];
    } else {
      nextConfig[key] = value;
    }
    settingsNode.config = nextConfig;

    syncNodeTargetEdges(settingsNode, getNodeDefinition(settingsNode));
    syncDefinitionInput();
    renderCanvas();
    renderSettingsPanel();
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

    workflowDefinition.edges.push({
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
        workflowDefinition.edges = workflowDefinition.edges.filter((item) => item.id !== edgeId);
      }
    } else {
      workflowDefinition.edges = workflowDefinition.edges.filter((item) => item.id !== edgeId);
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

    workflowDefinition.nodes = workflowDefinition.nodes.filter((candidate) => candidate.id !== nodeId);
    workflowDefinition.edges = workflowDefinition.edges.filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId,
    );

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
    if (!sourceNode || !canNodeEmitConnections(sourceNode)) {
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
  });

  canvas.nodeLayer.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) {
      return;
    }

    const target = event.target as HTMLElement;
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
      if (connectorNode && canNodeEmitConnections(connectorNode)) {
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

    const boardRect = canvas.board.getBoundingClientRect();
    const cursorX = event.clientX - boardRect.left + canvas.board.scrollLeft;
    const cursorY = event.clientY - boardRect.top + canvas.board.scrollTop;

    dragState = {
      nodeId,
      offsetX: cursorX - node.position.x,
      offsetY: cursorY - node.position.y,
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

    const boardRect = canvas.board.getBoundingClientRect();
    const cursorX = event.clientX - boardRect.left + canvas.board.scrollLeft;
    const cursorY = event.clientY - boardRect.top + canvas.board.scrollTop;

    updateNodePosition(dragState.nodeId, {
      x: cursorX - dragState.offsetX,
      y: cursorY - dragState.offsetY,
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
  });

  window.addEventListener('pointercancel', (event) => {
    stopConnecting(event.pointerId, event.clientX, event.clientY);
    stopDragging(event.pointerId);
  });

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
      updateSelectedNodeLabel(target.value);
      return;
    }

    const key = target.dataset.nodeSettingKey;
    if (!key) {
      return;
    }

    updateSelectedNodeField(key, target.value);
  });

  syncDefinitionInput();
  renderCanvas();
  renderBrowser();
  renderSettingsPanel();
}
