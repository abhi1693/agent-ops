import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from '../types';

export type GraphStore = {
  addEdge: (edge: WorkflowEdge) => void;
  addNode: (node: WorkflowNode) => void;
  commit: () => void;
  definition: WorkflowDefinition;
  getNode: (nodeId: string | null) => WorkflowNode | undefined;
  removeEdge: (edgeId: string) => void;
  removeNode: (nodeId: string) => void;
  replaceEdges: (edges: WorkflowEdge[]) => void;
  replaceNodes: (nodes: WorkflowNode[]) => void;
  setViewport: (viewport: WorkflowDefinition['viewport']) => void;
};

export function createGraphStore(params: {
  definition: WorkflowDefinition;
  persist: (definition: WorkflowDefinition) => void;
}): GraphStore {
  const { definition, persist } = params;

  return {
    addEdge(edge) {
      definition.edges.push(edge);
    },
    addNode(node) {
      definition.nodes.push(node);
    },
    commit() {
      persist(definition);
    },
    definition,
    getNode(nodeId) {
      if (!nodeId) {
        return undefined;
      }

      return definition.nodes.find((node) => node.id === nodeId);
    },
    removeEdge(edgeId) {
      definition.edges = definition.edges.filter((edge) => edge.id !== edgeId);
    },
    removeNode(nodeId) {
      definition.nodes = definition.nodes.filter((node) => node.id !== nodeId);
      definition.edges = definition.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId);
    },
    replaceEdges(edges) {
      definition.edges = edges;
    },
    replaceNodes(nodes) {
      definition.nodes = nodes;
    },
    setViewport(viewport) {
      definition.viewport = {
        x: viewport?.x ?? 0,
        y: viewport?.y ?? 0,
        zoom: viewport?.zoom ?? 1,
      };
    },
  };
}
