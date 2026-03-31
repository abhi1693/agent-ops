import type {
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowPersistedDefinition,
  WorkflowPersistedEdge,
  WorkflowPersistedNode,
} from '../types';

function normalizeNode(value: unknown): WorkflowNode | null {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const node = value as Partial<WorkflowPersistedNode>;
  const position =
    node.position && typeof node.position === 'object'
      ? (node.position as Partial<{ x: number; y: number }>)
      : {};
  const kind = typeof node.kind === 'string' && node.kind.trim() ? node.kind.trim() : '';
  const type = typeof node.type === 'string' && node.type.trim() ? node.type.trim() : '';

  if (!kind || !type || typeof node.id !== 'string' || !node.id.trim()) {
    return null;
  }

  return {
    config:
      node.config && typeof node.config === 'object' && !Array.isArray(node.config)
        ? node.config
        : {},
    id: node.id,
    kind,
    label: typeof node.label === 'string' ? node.label : '',
    position: {
      x: typeof position.x === 'number' ? position.x : 0,
      y: typeof position.y === 'number' ? position.y : 0,
    },
    type,
    typeVersion:
      typeof node.typeVersion === 'number' && Number.isFinite(node.typeVersion) && node.typeVersion > 0
        ? node.typeVersion
        : 1,
  };
}

function normalizeEdge(value: unknown): WorkflowEdge | null {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const edge = value as Partial<WorkflowPersistedEdge>;
  if (
    typeof edge.id !== 'string' ||
    !edge.id.trim() ||
    typeof edge.source !== 'string' ||
    !edge.source.trim() ||
    typeof edge.target !== 'string' ||
    !edge.target.trim()
  ) {
    return null;
  }

  return {
    id: edge.id,
    label: typeof edge.label === 'string' && edge.label.trim() ? edge.label : undefined,
    source: edge.source,
    sourcePort:
      typeof edge.sourcePort === 'string' && edge.sourcePort.trim() ? edge.sourcePort : undefined,
    target: edge.target,
    targetPort:
      typeof edge.targetPort === 'string' && edge.targetPort.trim() ? edge.targetPort : undefined,
  };
}

export function normalizeWorkflowDefinition(value: unknown): WorkflowDefinition {
  if (!value || typeof value !== 'object') {
    return { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } };
  }

  const definition = value as Partial<WorkflowPersistedDefinition>;

  return {
    nodes: Array.isArray(definition.nodes)
      ? definition.nodes.map(normalizeNode).filter((node): node is WorkflowNode => node !== null)
      : [],
    edges: Array.isArray(definition.edges)
      ? definition.edges.map(normalizeEdge).filter((edge): edge is WorkflowEdge => edge !== null)
      : [],
    viewport: definition.viewport ?? { x: 0, y: 0, zoom: 1 },
  };
}

function serializeWorkflowNode(node: WorkflowNode): WorkflowPersistedNode {
  const payload: WorkflowPersistedNode = {
    id: node.id,
    kind: node.kind,
    label: node.label,
    position: {
      x: node.position.x,
      y: node.position.y,
    },
    type: node.type,
  };

  if (node.config && Object.keys(node.config).length > 0) {
    payload.config = node.config;
  }
  if (node.typeVersion > 1) {
    payload.typeVersion = node.typeVersion;
  }

  return payload;
}

function serializeWorkflowEdge(edge: WorkflowEdge): WorkflowPersistedEdge {
  return {
    id: edge.id,
    ...(edge.label ? { label: edge.label } : {}),
    source: edge.source,
    ...(edge.sourcePort ? { sourcePort: edge.sourcePort } : {}),
    target: edge.target,
    ...(edge.targetPort ? { targetPort: edge.targetPort } : {}),
  };
}

export function serializeWorkflowDefinition(definition: WorkflowDefinition): WorkflowPersistedDefinition {
  return {
    nodes: definition.nodes.map(serializeWorkflowNode),
    edges: definition.edges.map(serializeWorkflowEdge),
    viewport: definition.viewport ?? { x: 0, y: 0, zoom: 1 },
  };
}
