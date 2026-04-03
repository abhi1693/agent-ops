import type { GraphStore } from './graphStore';
import type {
  AgentAuxiliaryPortId,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeTemplateField,
} from '../types';

export function createWorkflowDesignerGraphController(params: {
  createEdgeId: () => string;
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getNodeDefinition: (node: WorkflowNode | undefined) => WorkflowNodeDefinition | undefined;
  getWorkflowDefinition: () => WorkflowDefinition;
  getVisibleTargetFields: (
    node: WorkflowNode,
    nodeDefinition: WorkflowNodeDefinition | undefined,
  ) => WorkflowNodeTemplateField[];
  graphStore: GraphStore;
  isValidConnection: (
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ) => boolean;
  onClearHoveredEdge: () => void;
  onDeleteNodeStateCleanup: (nodeId: string) => void;
  renderBrowser: () => void;
  renderCanvas: () => void;
  renderSettingsPanel: () => void;
  showEmptyWorkflowBrowser: () => void;
  syncDefinitionInput: () => void;
}): {
  addEdge: (
    sourceId: string,
    targetId: string,
    options?: {
      sourcePort?: AgentAuxiliaryPortId;
      targetPort?: AgentAuxiliaryPortId;
    },
  ) => void;
  deleteNode: (nodeId: string) => void;
  removeEdge: (edgeId: string) => void;
  syncNodeTargetEdges: (node: WorkflowNode, nodeDefinition: WorkflowNodeDefinition | undefined) => void;
} {
  const {
    createEdgeId,
    getNode,
    getNodeDefinition,
    getWorkflowDefinition,
    getVisibleTargetFields,
    graphStore,
    isValidConnection,
    onClearHoveredEdge,
    onDeleteNodeStateCleanup,
    renderBrowser,
    renderCanvas,
    renderSettingsPanel,
    showEmptyWorkflowBrowser,
    syncDefinitionInput,
  } = params;

  function syncNodeTargetEdges(node: WorkflowNode, nodeDefinition: WorkflowNodeDefinition | undefined): void {
    const workflowDefinition = getWorkflowDefinition();
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
        id: createEdgeId(),
        source: node.id,
        target: targetId,
      });
    });
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
      id: createEdgeId(),
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
    const workflowDefinition = getWorkflowDefinition();
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

    onClearHoveredEdge();
    syncDefinitionInput();
    renderCanvas();
    renderSettingsPanel();
  }

  function deleteNode(nodeId: string): void {
    const workflowDefinition = getWorkflowDefinition();
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
    onDeleteNodeStateCleanup(nodeId);

    if (workflowDefinition.nodes.length === 0) {
      showEmptyWorkflowBrowser();
    }

    syncDefinitionInput();
    renderCanvas();
    renderBrowser();
    renderSettingsPanel();
  }

  return {
    addEdge,
    deleteNode,
    removeEdge,
    syncNodeTargetEdges,
  };
}
