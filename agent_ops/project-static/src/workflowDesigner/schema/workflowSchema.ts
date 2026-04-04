import type {
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowPersistedDefinition,
  WorkflowPersistedEdge,
  WorkflowPersistedNode,
} from '../types';

const WORKFLOW_DEFINITION_VERSION = 2;

type WorkflowSchemaOptions = {
  kindByType?: Record<string, string>;
};

function normalizeNode(value: unknown, options?: WorkflowSchemaOptions): WorkflowNode | null {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const node = value as Partial<WorkflowPersistedNode>;
  const position =
    node.position && typeof node.position === 'object'
      ? (node.position as Partial<{ x: number; y: number }>)
      : {};
  const kind =
    typeof node.kind === 'string' && node.kind.trim()
      ? node.kind.trim()
      : typeof options?.kindByType?.[typeof node.type === 'string' ? node.type : ''] === 'string' &&
          options.kindByType[typeof node.type === 'string' ? node.type : ''].trim()
        ? options.kindByType[typeof node.type === 'string' ? node.type : ''].trim()
        : '';
  const type = typeof node.type === 'string' && node.type.trim() ? node.type.trim() : '';

  if (!kind || !type || typeof node.id !== 'string' || !node.id.trim()) {
    return null;
  }

  const persistedConfig =
    node.config && typeof node.config === 'object' && !Array.isArray(node.config) ? node.config : {};
  const persistedParameters =
    node.parameters && typeof node.parameters === 'object' && !Array.isArray(node.parameters) ? node.parameters : {};
  const config: Record<string, unknown> = {
    ...persistedConfig,
    ...persistedParameters,
  };
  if (node.connection_id !== undefined && node.connection_id !== null && node.connection_id !== '') {
    config.connection_id = node.connection_id;
  }

  return {
    config,
    disabled: node.disabled === true,
    id: node.id,
    kind,
    label:
      typeof node.name === 'string' && node.name.trim()
        ? node.name
        : typeof node.label === 'string'
          ? node.label
          : '',
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
      typeof edge.sourcePort === 'string' && edge.sourcePort.trim()
        ? edge.sourcePort
        : typeof edge.source_port === 'string' && edge.source_port.trim()
          ? edge.source_port
          : undefined,
    target: edge.target,
    targetPort:
      typeof edge.targetPort === 'string' && edge.targetPort.trim()
        ? edge.targetPort
        : typeof edge.target_port === 'string' && edge.target_port.trim()
          ? edge.target_port
          : undefined,
  };
}

export function normalizeWorkflowDefinition(
  value: unknown,
  options?: WorkflowSchemaOptions,
): WorkflowDefinition {
  if (!value || typeof value !== 'object') {
    return { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } };
  }

  const definition = value as Partial<WorkflowPersistedDefinition>;

  return {
    nodes: Array.isArray(definition.nodes)
      ? definition.nodes
          .map((node) => normalizeNode(node, options))
          .filter((node): node is WorkflowNode => node !== null)
      : [],
    edges: Array.isArray(definition.edges)
      ? definition.edges.map(normalizeEdge).filter((edge): edge is WorkflowEdge => edge !== null)
      : [],
    viewport: definition.viewport ?? { x: 0, y: 0, zoom: 1 },
  };
}

function serializeWorkflowNode(node: WorkflowNode): WorkflowPersistedNode {
  const payload: WorkflowPersistedNode = {
    ...(node.disabled ? { disabled: true } : {}),
    id: node.id,
    kind: node.kind,
    name: node.label,
    position: {
      x: node.position.x,
      y: node.position.y,
    },
    type: node.type,
  };

  if (node.config) {
    const parameters: Record<string, unknown> = { ...node.config };
    const connectionId = parameters.connection_id;
    delete parameters.connection_id;
    if (connectionId !== undefined && connectionId !== null && connectionId !== '') {
      payload.connection_id = connectionId as string | number;
    }
    if (Object.keys(parameters).length > 0) {
      payload.parameters = parameters;
    }
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
    ...(edge.sourcePort ? { source_port: edge.sourcePort } : {}),
    target: edge.target,
    ...(edge.targetPort ? { target_port: edge.targetPort } : {}),
  };
}

export function serializeWorkflowDefinition(definition: WorkflowDefinition): WorkflowPersistedDefinition {
  return {
    definition_version: WORKFLOW_DEFINITION_VERSION,
    nodes: definition.nodes.map(serializeWorkflowNode),
    edges: definition.edges.map(serializeWorkflowEdge),
    viewport: definition.viewport ?? { x: 0, y: 0, zoom: 1 },
  };
}
