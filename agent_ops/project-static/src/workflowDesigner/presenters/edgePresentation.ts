import {
  buildConnectionPath,
  getAgentAuxiliaryPortPoint,
  getConnectionMidpoint,
  getConnectorPoint,
  getEdgeAnchors,
  getNodeCenter,
  getOppositeConnectorSide,
  getPreferredConnectorSide,
} from '../geometry';
import type {
  AgentAuxiliaryPortId,
  ConnectorSide,
  Point,
  WorkflowDefinition,
  WorkflowEditorEdgesPresentation,
  WorkflowNode,
} from '../types';
import { clamp } from '../utils';

type ConnectionDraftInput = {
  hoveredTargetId: string | null;
  hoveredTargetPort: AgentAuxiliaryPortId | null;
  hoveredTargetSide: ConnectorSide | null;
  pointerX: number;
  pointerY: number;
  sourceId: string;
};

function buildDraftPath(params: {
  connectionDraft: ConnectionDraftInput | null;
  getNode: (nodeId: string) => WorkflowNode | undefined;
}): string | null {
  const { connectionDraft, getNode } = params;

  if (!connectionDraft) {
    return null;
  }

  const sourceNode = getNode(connectionDraft.sourceId);
  if (!sourceNode) {
    return null;
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

  return buildConnectionPath(sourcePoint, sourceSide, targetPoint, targetSide);
}

function buildHoveredControl(params: {
  boardHeight: number;
  boardWidth: number;
  connectionDraft: ConnectionDraftInput | null;
  dragActive: boolean;
  getNode: (nodeId: string) => WorkflowNode | undefined;
  hoveredEdgeId: string | null;
  viewportWorldToScreen: (point: Point) => Point;
  workflowDefinition: WorkflowDefinition;
}): WorkflowEditorEdgesPresentation['hoveredControl'] {
  const {
    boardHeight,
    boardWidth,
    connectionDraft,
    dragActive,
    getNode,
    hoveredEdgeId,
    viewportWorldToScreen,
    workflowDefinition,
  } = params;

  if (dragActive || connectionDraft || !hoveredEdgeId) {
    return null;
  }

  const hoveredEdge = workflowDefinition.edges.find((edge) => edge.id === hoveredEdgeId);
  if (!hoveredEdge) {
    return null;
  }

  const sourceNode = getNode(hoveredEdge.source);
  const targetNode = getNode(hoveredEdge.target);
  if (!sourceNode || !targetNode) {
    return null;
  }

  const { sourcePoint, sourceSide, targetPoint, targetSide } = getEdgeAnchors(
    hoveredEdge,
    sourceNode,
    targetNode,
  );
  const midpoint = getConnectionMidpoint(sourcePoint, sourceSide, targetPoint, targetSide);
  const controlPoint = viewportWorldToScreen(midpoint);

  return {
    edgeId: hoveredEdge.id,
    x: clamp(Math.round(controlPoint.x), 20, Math.max(boardWidth - 20, 20)),
    y: clamp(Math.round(controlPoint.y), 20, Math.max(boardHeight - 20, 20)),
  };
}

export function buildWorkflowEditorEdgesPresentation(params: {
  boardHeight: number;
  boardWidth: number;
  connectionDraft: ConnectionDraftInput | null;
  dragActive: boolean;
  getNode: (nodeId: string) => WorkflowNode | undefined;
  hoveredEdgeId: string | null;
  viewportWorldToScreen: (point: Point) => Point;
  workflowDefinition: WorkflowDefinition;
}): WorkflowEditorEdgesPresentation {
  const {
    boardHeight,
    boardWidth,
    connectionDraft,
    dragActive,
    getNode,
    hoveredEdgeId,
    viewportWorldToScreen,
    workflowDefinition,
  } = params;

  const edges = workflowDefinition.edges.reduce<WorkflowEditorEdgesPresentation['edges']>((items, edge) => {
    const sourceNode = getNode(edge.source);
    const targetNode = getNode(edge.target);
    if (!sourceNode || !targetNode) {
      return items;
    }

    const { sourcePoint, sourceSide, targetPoint, targetSide } = getEdgeAnchors(
      edge,
      sourceNode,
      targetNode,
    );

    items.push({
      id: edge.id,
      isHovered: hoveredEdgeId === edge.id,
      path: buildConnectionPath(sourcePoint, sourceSide, targetPoint, targetSide),
    });
    return items;
  }, []);

  return {
    draftPath: buildDraftPath({ connectionDraft, getNode }),
    edges,
    hoveredControl: buildHoveredControl({
      boardHeight,
      boardWidth,
      connectionDraft,
      dragActive,
      getNode,
      hoveredEdgeId,
      viewportWorldToScreen,
      workflowDefinition,
    }),
  };
}
