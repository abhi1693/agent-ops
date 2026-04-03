import {
  getAgentAuxiliaryPortPoint,
  getConnectorPoint,
  getNodeCenter,
  getPreferredConnectorSide,
} from '../geometry';
import type {
  AgentAuxiliaryPortId,
  ConnectorSide,
  Point,
  WorkflowAgentAuxiliaryPort,
  WorkflowDefinition,
  WorkflowEditorNodePresentation,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeTemplateField,
  WorkflowNodeTemplateOption,
} from '../types';
import {
  formatKindLabel,
  getConfigString,
  getTemplateFieldOptions,
  getTemplateFieldValue,
} from '../utils';

type ConnectionDraftInput = {
  hoveredTargetId: string | null;
  hoveredTargetPort: AgentAuxiliaryPortId | null;
  hoveredTargetSide: ConnectorSide | null;
  pointerX: number;
  pointerY: number;
  sourceId: string;
};

function getDefinitionField(
  definition: WorkflowNodeDefinition | undefined,
  key: string,
): WorkflowNodeTemplateField | undefined {
  return definition?.fields.find((field) => field.key === key);
}

export function getFieldOptionsWithCurrentValue(
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

function getDraftTargetPoint(params: {
  canEmitConnections: boolean;
  connectionDraft: ConnectionDraftInput | null;
  getNode: (nodeId: string) => WorkflowNode | undefined;
  isConnectionSource: boolean;
}): Point | null {
  const {
    canEmitConnections,
    connectionDraft,
    getNode,
    isConnectionSource,
  } = params;

  if (!connectionDraft || !isConnectionSource || !canEmitConnections) {
    return null;
  }

  if (!connectionDraft.hoveredTargetId) {
    return {
      x: connectionDraft.pointerX,
      y: connectionDraft.pointerY,
    };
  }

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

  if (connectionDraft.hoveredTargetSide) {
    return getConnectorPoint(hoveredNode, connectionDraft.hoveredTargetSide);
  }

  return getNodeCenter(hoveredNode);
}

export function buildWorkflowEditorNodePresentation(params: {
  activeExecutionNodeId: string | null;
  auxiliaryPortDefinitions: WorkflowAgentAuxiliaryPort[];
  canNodeEmitConnections: (
    node: WorkflowNode,
    edges: WorkflowDefinition['edges'],
    definition?: WorkflowNodeDefinition,
  ) => boolean;
  canNodeReceiveConnections: (
    node: WorkflowNode,
    edges: WorkflowDefinition['edges'],
    definition?: WorkflowNodeDefinition,
  ) => boolean;
  connectionDraft: ConnectionDraftInput | null;
  connectorSides: ConnectorSide[];
  executionActiveNodeIds: string[];
  executionFailedNodeIds: string[];
  executionSucceededNodeId: string | null;
  getCompatibleAgentAuxiliaryPort: (
    sourceNode: WorkflowNode | undefined,
    sourceDefinition: WorkflowNodeDefinition | undefined,
    targetNode: WorkflowNode | undefined,
  ) => AgentAuxiliaryPortId | null;
  getNode: (nodeId: string) => WorkflowNode | undefined;
  getNodeDefinition: (node: WorkflowNode | undefined) => WorkflowNodeDefinition | undefined;
  isExecutionPending: boolean;
  isValidConnection: (
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ) => boolean;
  node: WorkflowNode;
  nodeDefinition: WorkflowNodeDefinition | undefined;
  selectedNodeId: string | null;
  workflowDefinition: WorkflowDefinition;
}): WorkflowEditorNodePresentation {
  const {
    activeExecutionNodeId,
    auxiliaryPortDefinitions,
    canNodeEmitConnections,
    canNodeReceiveConnections,
    connectionDraft,
    connectorSides,
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
  } = params;

  const icon = nodeDefinition?.icon ?? 'mdi-vector-square';
  const title = node.label || nodeDefinition?.label || formatKindLabel(node.kind) || node.type;
  const isDefaultAgentTitle = node.kind === 'agent' && title === (nodeDefinition?.label ?? 'Agent');
  const agentDisplayTitle = node.kind === 'agent' && isDefaultAgentTitle ? 'AI Agent' : title;
  const showAgentKindLabel = node.kind === 'agent' && !isDefaultAgentTitle;
  const isSelected = selectedNodeId === node.id;
  const isExecutionNodePending =
    executionActiveNodeIds.includes(node.id)
    || (isExecutionPending && activeExecutionNodeId === node.id);
  const isExecutionSucceeded = executionSucceededNodeId === node.id;
  const isExecutionFailed = executionFailedNodeIds.includes(node.id);
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
  const draftTargetPoint = getDraftTargetPoint({
    canEmitConnections,
    connectionDraft,
    getNode,
    isConnectionSource,
  });
  const activeSourceSide = draftTargetPoint ? getPreferredConnectorSide(node, draftTargetPoint) : null;
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
  const agentNeedsModel = node.kind === 'agent' && modelConnections.length === 0;
  const connectors = shouldRenderConnectors
    ? connectorSides.map((side) => ({
        isCandidate: isConnectionCandidate,
        isInputActive: activeTargetSide === side,
        isOutputActive: activeSourceSide === side,
        modeClass: connectorModeClass,
        nodeId: node.id,
        side,
      }))
    : [];
  const auxiliaryPorts = node.kind === 'agent'
    ? auxiliaryPortDefinitions.map((port) => {
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

        return {
          actionIcon,
          ariaLabel: connectionCount > 0 && port.id === 'ai_languageModel'
            ? `${connectedModelStateLabel ?? port.label}`
            : `Add ${port.label}`,
          id: port.id,
          isActive: isActiveTargetPort,
          isCandidate: isCompatibleCandidate,
          isConnected: connectionCount > 0,
          isWarning: port.id === 'ai_languageModel' && connectionCount === 0,
          label: port.label,
          modelProviderAppId,
          nodeId: node.id,
          stateLabel,
          title: connectionCount > 0 && port.id === 'ai_languageModel'
            ? `${connectedModelStateLabel ?? port.label}`
            : `Add ${port.label}`,
        };
      })
    : [];

  return {
    agentDisplayTitle,
    agentNeedsModel,
    auxiliaryPorts,
    connectors,
    icon,
    isConnectionCandidate,
    isConnectionSource,
    isConnectionTarget,
    isExecutionFailed,
    isExecutionPending: isExecutionNodePending,
    isExecutionSucceeded,
    isSelected,
    node,
    showAgentKindLabel,
    title,
  };
}
