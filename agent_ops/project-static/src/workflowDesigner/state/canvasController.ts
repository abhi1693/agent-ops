import {
  clampNodePosition,
  getGraphBounds,
  getNodeCenter,
  getNodeRenderHeight,
  getNodeRenderWidth,
} from '../geometry';
import { getHoveredTarget as getHoveredConnectionTarget } from '../interactions/connections';
import type {
  AgentAuxiliaryPortId,
  ConnectorSide,
  Point,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
} from '../types';
import { clamp } from '../utils';

type ViewportCanvasController = {
  fitBounds: (bounds: { height: number; minX: number; minY: number; width: number } | null, options?: { padding?: number }) => void;
  focusPoint: (point: Point) => void;
  getBoardLocalPoint: (clientX: number, clientY: number) => Point;
  screenToWorld: (clientX: number, clientY: number) => Point;
};

export function createWorkflowDesignerCanvasController(params: {
  board: HTMLElement;
  contextMenuHeight: number;
  contextMenuMargin: number;
  contextMenuOffsetX: number;
  contextMenuOffsetY: number;
  contextMenuWidth: number;
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getNodeDefinition: (node: WorkflowNode | undefined) => WorkflowNodeDefinition | undefined;
  getWorkflowDefinition: () => WorkflowDefinition;
  isValidConnection: (
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ) => boolean;
  nodeLayer: HTMLElement;
  renderEdges: () => void;
  syncDefinitionInput: () => void;
  viewportController: ViewportCanvasController;
}): {
  getHoveredTarget: (
    clientX: number,
    clientY: number,
    sourceId: string,
  ) => { nodeId: string; side: ConnectorSide; targetPort: AgentAuxiliaryPortId | null } | null;
  getNodeContextMenuPosition: (clientX: number, clientY: number) => { x: number; y: number };
  getNodeElement: (nodeId: string) => HTMLElement | null;
  getPointFromClient: (clientX: number, clientY: number) => Point;
  repositionGraph: (anchorNodeId?: string) => void;
  updateNodePosition: (nodeId: string, position: { x: number; y: number }) => void;
} {
  const {
    board,
    contextMenuHeight,
    contextMenuMargin,
    contextMenuOffsetX,
    contextMenuOffsetY,
    contextMenuWidth,
    getNode,
    getNodeDefinition,
    getWorkflowDefinition,
    isValidConnection,
    nodeLayer,
    renderEdges,
    syncDefinitionInput,
    viewportController,
  } = params;

  function getNodeElement(nodeId: string): HTMLElement | null {
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
      getNode: (nodeId) => getNode(nodeId ?? null),
      getPointFromClient,
      isValidConnection,
      sourceId,
    });
  }

  function getNodeContextMenuPosition(clientX: number, clientY: number): { x: number; y: number } {
    const localPoint = viewportController.getBoardLocalPoint(clientX, clientY);
    const rawX = localPoint.x + contextMenuOffsetX;
    const rawY = localPoint.y + contextMenuOffsetY;
    const minX = contextMenuMargin;
    const minY = contextMenuMargin;
    const maxX = Math.max(
      minX,
      board.clientWidth - contextMenuWidth - contextMenuMargin,
    );
    const maxY = Math.max(
      minY,
      board.clientHeight - contextMenuHeight - contextMenuMargin,
    );

    return {
      x: clamp(Math.round(rawX), minX, maxX),
      y: clamp(Math.round(rawY), minY, maxY),
    };
  }

  function repositionGraph(anchorNodeId?: string): void {
    const workflowDefinition = getWorkflowDefinition();
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

  function updateNodePosition(nodeId: string, position: { x: number; y: number }): void {
    const workflowDefinition = getWorkflowDefinition();
    const node = workflowDefinition.nodes.find((item) => item.id === nodeId);
    if (!node) {
      return;
    }

    node.position = clampNodePosition(
      board,
      position,
      getNodeRenderHeight(node),
      getNodeRenderWidth(node),
    );
    syncDefinitionInput();

    const nodeElement = getNodeElement(nodeId);
    if (nodeElement) {
      setNodeElementPosition(nodeElement, node);
    }

    renderEdges();
  }

  return {
    getHoveredTarget,
    getNodeContextMenuPosition,
    getNodeElement,
    getPointFromClient,
    repositionGraph,
    updateNodePosition,
  };
}
