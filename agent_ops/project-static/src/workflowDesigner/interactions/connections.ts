import { getPreferredConnectorSide } from '../geometry';
import { isModelDefinition, isToolCompatibleDefinition } from '../registry/modelDefinitions';
import type {
  AgentAuxiliaryPortId,
  ConnectorSide,
  Point,
  WorkflowAgentAuxiliaryPort,
  WorkflowConnectionHoverTarget,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
} from '../types';

export const AGENT_AUXILIARY_PORTS: WorkflowAgentAuxiliaryPort[] = [
  {
    id: 'ai_languageModel',
    label: 'Model',
  },
  {
    id: 'ai_tool',
    label: 'Tools',
  },
];

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

function hasConnection(
  edges: WorkflowDefinition['edges'],
  sourceId: string,
  targetId: string,
  targetPort?: string | null,
): boolean {
  return edges.some(
    (edge) =>
      edge.source === sourceId &&
      edge.target === targetId &&
      (edge.targetPort ?? null) === (targetPort ?? null),
  );
}

export function canNodeReceiveConnections(
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

export function canNodeEmitConnections(
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

export function getCompatibleAgentAuxiliaryPort(
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

export function getAgentAuxiliaryPortDefinition(
  portId: AgentAuxiliaryPortId | null | undefined,
): WorkflowAgentAuxiliaryPort | undefined {
  if (!portId) {
    return undefined;
  }

  return AGENT_AUXILIARY_PORTS.find((port) => port.id === portId);
}

export function getAgentAuxiliaryAllowedNodeTypes(
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

export function isValidConnection(params: {
  getNode: (nodeId: string | null) => WorkflowNode | undefined;
  getNodeDefinition: (node: WorkflowNode | undefined) => WorkflowNodeDefinition | undefined;
  sourceId: string;
  targetId: string;
  targetPort?: AgentAuxiliaryPortId | null;
  workflowDefinition: WorkflowDefinition;
}): boolean {
  const {
    getNode,
    getNodeDefinition,
    sourceId,
    targetId,
    targetPort,
    workflowDefinition,
  } = params;

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

    if (hasConnection(workflowDefinition.edges, sourceId, targetId, targetPort)) {
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

  return !hasConnection(workflowDefinition.edges, sourceId, targetId, null);
}

export function getHoveredTarget(params: {
  clientX: number;
  clientY: number;
  getElementFromPoint: (clientX: number, clientY: number) => HTMLElement | null;
  getNode: (nodeId: string | null) => WorkflowNode | undefined;
  getPointFromClient: (clientX: number, clientY: number) => Point;
  isValidConnection: (
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ) => boolean;
  sourceId: string;
}): WorkflowConnectionHoverTarget | null {
  const {
    clientX,
    clientY,
    getElementFromPoint,
    getNode,
    getPointFromClient,
    isValidConnection,
    sourceId,
  } = params;

  const target = getElementFromPoint(clientX, clientY);
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
