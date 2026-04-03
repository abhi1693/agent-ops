import {
  CANVAS_EDGE_MARGIN,
  NODE_CARD_HEIGHT,
  NODE_CARD_WIDTH,
  NODE_COLUMN_GAP,
  NODE_HEIGHT,
  NODE_ROW_GAP,
  NODE_WIDTH,
  SURFACE_PADDING,
} from './constants';
import type {
  AgentAuxiliaryPortId,
  ConnectorSide,
  Point,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
} from './types';
import { clamp } from './utils';

const AGENT_NODE_WIDTH = 224;
const AGENT_NODE_HEIGHT = 164;
const AGENT_NODE_CARD_WIDTH = 224;
const AGENT_NODE_CARD_HEIGHT = 164;
const AGENT_AUXILIARY_PORT_ANCHOR_X = 18;
const AGENT_AUXILIARY_PORT_ANCHOR_Y = 102;
const AGENT_AUXILIARY_PORT_ROW_GAP = 34;

export function getBoardBounds(
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

export function clampNodePosition(
  board: HTMLElement,
  position: Point,
  nodeHeight = NODE_HEIGHT,
  nodeWidth = NODE_WIDTH,
): Point {
  const bounds = getBoardBounds(board, nodeHeight, nodeWidth);

  return {
    x: clamp(Math.round(position.x), CANVAS_EDGE_MARGIN, bounds.maxX),
    y: clamp(Math.round(position.y), CANVAS_EDGE_MARGIN, bounds.maxY),
  };
}

export function getNodeRenderWidth(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return node?.kind === 'agent' ? AGENT_NODE_WIDTH : NODE_WIDTH;
}

export function getNodeRenderHeight(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return node?.kind === 'agent' ? AGENT_NODE_HEIGHT : NODE_HEIGHT;
}

export function getNodeCardWidth(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return node?.kind === 'agent' ? AGENT_NODE_CARD_WIDTH : NODE_CARD_WIDTH;
}

export function getNodeCardHeight(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return node?.kind === 'agent' ? AGENT_NODE_CARD_HEIGHT : NODE_CARD_HEIGHT;
}

function getNodeCardOffsetX(node: Pick<WorkflowNode, 'kind'> | null | undefined): number {
  return (getNodeRenderWidth(node) - getNodeCardWidth(node)) / 2;
}

export function getGraphBounds(nodes: WorkflowNode[]): {
  height: number;
  maxX: number;
  maxY: number;
  minX: number;
  minY: number;
  width: number;
} | null {
  if (nodes.length === 0) {
    return null;
  }

  const minX = Math.min(...nodes.map((node) => node.position.x));
  const minY = Math.min(...nodes.map((node) => node.position.y));
  const maxX = Math.max(...nodes.map((node) => node.position.x + getNodeRenderWidth(node)));
  const maxY = Math.max(...nodes.map((node) => node.position.y + getNodeRenderHeight(node)));

  return {
    height: maxY - minY,
    maxX,
    maxY,
    minX,
    minY,
    width: maxX - minX,
  };
}

function nodesOverlap(
  first: Point,
  second: Point,
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

export function hasNodeCollision(
  definition: WorkflowDefinition,
  position: Point,
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

export function getSuggestedNodePosition(
  board: HTMLElement,
  definition: WorkflowDefinition,
  selectedNodeId: string | null,
  nextNode: Pick<WorkflowNode, 'kind'> | null | undefined,
): Point {
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

export function getNodeCenter(node: WorkflowNode): Point {
  return {
    x: node.position.x + getNodeCardOffsetX(node) + getNodeCardWidth(node) / 2,
    y: node.position.y + getNodeCardHeight(node) / 2,
  };
}

export function getConnectorPoint(node: WorkflowNode, side: ConnectorSide): Point {
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

export function getAgentAuxiliaryPortPoint(node: WorkflowNode, portId: AgentAuxiliaryPortId): Point {
  const portIndex = portId === 'ai_tool' ? 1 : 0;

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

export function getOppositeConnectorSide(side: ConnectorSide): ConnectorSide {
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

export function getPreferredConnectorSide(node: WorkflowNode, point: Point): ConnectorSide {
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

function getConnectionControlOffset(
  source: Point,
  target: Point,
): number {
  return Math.max(Math.max(Math.abs(target.x - source.x), Math.abs(target.y - source.y)) * 0.4, 64);
}

export function buildConnectionPath(
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

export function getConnectionMidpoint(
  source: Point,
  sourceSide: ConnectorSide,
  target: Point,
  targetSide: ConnectorSide,
): Point {
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

export function getEdgeAnchors(
  edge: WorkflowEdge,
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
