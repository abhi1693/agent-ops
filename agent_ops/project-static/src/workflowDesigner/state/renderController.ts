import type { CanvasElements } from '../dom';
import {
  renderEdgeRemoveButtonMarkup,
  renderNodeContextMenuMarkup,
  renderWorkflowEditorEdgesMarkup,
  renderWorkflowEditorNodeMarkup,
} from '../markup';
import { buildWorkflowEditorEdgesPresentation } from '../presenters/edgePresentation';
import { buildWorkflowEditorNodePresentation } from '../presenters/nodePresentation';
import type {
  AgentAuxiliaryPortId,
  ConnectorSide,
  Point,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
} from '../types';
import { formatKindLabel } from '../utils';
import type { WorkflowNodeContextMenuState } from './selectionController';
import {
  AGENT_AUXILIARY_PORTS,
  canNodeEmitConnections,
  canNodeReceiveConnections,
  getCompatibleAgentAuxiliaryPort,
} from '../interactions/connections';

const CONNECTOR_SIDES: ConnectorSide[] = ['top', 'right', 'bottom', 'left'];

type ConnectionDraftInput = {
  hoveredTargetId: string | null;
  hoveredTargetPort: AgentAuxiliaryPortId | null;
  hoveredTargetSide: ConnectorSide | null;
  pointerX: number;
  pointerY: number;
  sourceId: string;
} | null;

export function createWorkflowDesignerRenderController(params: {
  canvas: CanvasElements;
  clearContextMenuState: () => void;
  getActiveExecutionNodeId: () => string | null;
  getAppLabel: (definition: WorkflowNodeDefinition | undefined) => string;
  getConnectionDraft: () => ConnectionDraftInput;
  getContextMenuState: () => WorkflowNodeContextMenuState | null;
  getExecutionActiveNodeIds: () => string[];
  getExecutionFailedNodeIds: () => string[];
  getExecutionSucceededNodeId: () => string | null;
  getHoveredEdgeId: () => string | null;
  getIsExecutionPending: () => boolean;
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getNodeDefinition: (node: WorkflowNode | undefined) => WorkflowNodeDefinition | undefined;
  getSelectedNodeId: () => string | null;
  getViewportZoom: () => number;
  getWorkflowDefinition: () => WorkflowDefinition;
  isValidConnection: (
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ) => boolean;
  isDragActive: () => boolean;
  isEmptyWorkflow: () => boolean;
  viewportWorldToScreen: (point: Point) => Point;
}): {
  renderCanvas: () => void;
  renderCanvasHud: () => void;
  renderEdges: () => void;
  renderEmptyState: () => void;
  renderNodeContextMenu: () => void;
  renderNodes: () => void;
} {
  const {
    canvas,
    clearContextMenuState,
    getActiveExecutionNodeId,
    getAppLabel,
    getConnectionDraft,
    getContextMenuState,
    getExecutionActiveNodeIds,
    getExecutionFailedNodeIds,
    getExecutionSucceededNodeId,
    getHoveredEdgeId,
    getIsExecutionPending,
    getNode,
    getNodeDefinition,
    getSelectedNodeId,
    getViewportZoom,
    getWorkflowDefinition,
    isValidConnection,
    isDragActive,
    isEmptyWorkflow,
    viewportWorldToScreen,
  } = params;

  function getNodeElement(nodeId: string): HTMLElement | null {
    return (
      Array.from(canvas.nodeLayer.querySelectorAll<HTMLElement>('[data-workflow-node-id]')).find(
        (element) => element.dataset.workflowNodeId === nodeId,
      ) ?? null
    );
  }

  function setNodeElementPosition(nodeElement: HTMLElement, node: WorkflowNode): void {
    nodeElement.style.left = `${node.position.x}px`;
    nodeElement.style.top = `${node.position.y}px`;
  }

  function renderNodeContextMenu(): void {
    const contextMenuState = getContextMenuState();
    if (!contextMenuState) {
      canvas.nodeMenu.hidden = true;
      canvas.nodeMenu.innerHTML = '';
      return;
    }

    const node = getNode(contextMenuState.nodeId);
    if (!node) {
      clearContextMenuState();
      canvas.nodeMenu.hidden = true;
      canvas.nodeMenu.innerHTML = '';
      return;
    }

    const title = node.label || formatKindLabel(node.kind) || node.type;
    const nodeDefinition = getNodeDefinition(node);
    const appLabel = getAppLabel(nodeDefinition);
    const meta = [
      formatKindLabel(node.kind),
      nodeDefinition?.catalog_section === 'apps' && appLabel && appLabel !== 'Workflow'
        ? appLabel
        : null,
    ]
      .filter((value): value is string => Boolean(value))
      .join(' • ');
    canvas.nodeMenu.hidden = false;
    canvas.nodeMenu.style.left = `${contextMenuState.x}px`;
    canvas.nodeMenu.style.top = `${contextMenuState.y}px`;
    canvas.nodeMenu.innerHTML = renderNodeContextMenuMarkup({ meta, title });
  }

  function renderEmptyState(): void {
    const emptyWorkflow = isEmptyWorkflow();
    canvas.board.classList.toggle('is-empty-workflow', emptyWorkflow);
    canvas.emptyState.hidden = !emptyWorkflow;
  }

  function renderCanvasHud(): void {
    const zoom = getViewportZoom();
    const workflowDefinition = getWorkflowDefinition();
    canvas.fitViewButton.disabled = workflowDefinition.nodes.length === 0;
    canvas.zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
    canvas.zoomOutButton.disabled = zoom <= 0.46;
    canvas.zoomInButton.disabled = zoom >= 1.79;
  }

  function renderNodes(): void {
    const workflowDefinition = getWorkflowDefinition();
    const connectionDraft = getConnectionDraft();
    canvas.nodeLayer.innerHTML = workflowDefinition.nodes
      .map((node) => {
        const nodeDefinition = getNodeDefinition(node);
        return renderWorkflowEditorNodeMarkup(
          buildWorkflowEditorNodePresentation({
            activeExecutionNodeId: getActiveExecutionNodeId(),
            auxiliaryPortDefinitions: AGENT_AUXILIARY_PORTS,
            canNodeEmitConnections,
            canNodeReceiveConnections,
            connectionDraft,
            connectorSides: CONNECTOR_SIDES,
            executionActiveNodeIds: getExecutionActiveNodeIds(),
            executionFailedNodeIds: getExecutionFailedNodeIds(),
            executionSucceededNodeId: getExecutionSucceededNodeId(),
            getCompatibleAgentAuxiliaryPort,
            getNode: (nodeId) => getNode(nodeId ?? null),
            getNodeDefinition,
            isExecutionPending: getIsExecutionPending(),
            isValidConnection,
            node,
            nodeDefinition,
            selectedNodeId: getSelectedNodeId(),
            workflowDefinition,
          }),
        );
      })
      .join('');

    workflowDefinition.nodes.forEach((node) => {
      const nodeElement = getNodeElement(node.id);
      if (nodeElement) {
        setNodeElementPosition(nodeElement, node);
      }
    });
  }

  function renderEdges(): void {
    const workflowDefinition = getWorkflowDefinition();
    const connectionDraft = getConnectionDraft();
    canvas.edgeLayer.setAttribute(
      'viewBox',
      `0 0 ${Math.max(canvas.board.clientWidth, 1)} ${Math.max(canvas.board.clientHeight, 1)}`,
    );
    const edgePresentation = buildWorkflowEditorEdgesPresentation({
      boardHeight: canvas.board.clientHeight,
      boardWidth: canvas.board.clientWidth,
      connectionDraft,
      dragActive: isDragActive(),
      getNode: (nodeId) => getNode(nodeId ?? null),
      hoveredEdgeId: getHoveredEdgeId(),
      viewportWorldToScreen,
      workflowDefinition,
    });

    canvas.edgeLayer.innerHTML = renderWorkflowEditorEdgesMarkup(edgePresentation);
    canvas.edgeControls.innerHTML = edgePresentation.hoveredControl
      ? renderEdgeRemoveButtonMarkup(edgePresentation.hoveredControl)
      : '';
  }

  function renderCanvas(): void {
    renderNodes();
    renderEdges();
    renderEmptyState();
    renderCanvasHud();
    renderNodeContextMenu();
  }

  return {
    renderCanvas,
    renderCanvasHud,
    renderEdges,
    renderEmptyState,
    renderNodeContextMenu,
    renderNodes,
  };
}
