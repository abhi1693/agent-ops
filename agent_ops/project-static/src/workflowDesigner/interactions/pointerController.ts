import type { CanvasElements } from '../dom';
import type {
  AgentAuxiliaryPortId,
  Point,
  WorkflowConnectionHoverTarget,
  WorkflowNode,
} from '../types';

export type DragState = {
  nodeId: string;
  offsetX: number;
  offsetY: number;
  pointerId: number;
};

export type PanState = {
  didMove: boolean;
  lastClientX: number;
  lastClientY: number;
  pointerId: number;
};

export type ConnectionDraft = {
  hoveredTargetId: string | null;
  hoveredTargetPort: AgentAuxiliaryPortId | null;
  hoveredTargetSide: WorkflowConnectionHoverTarget['side'] | null;
  pointerId: number;
  pointerX: number;
  pointerY: number;
  sourceId: string;
};

type PointerViewportController = {
  panBy(deltaX: number, deltaY: number): void;
  screenToWorld(clientX: number, clientY: number): Point;
  zoomAt(clientX: number, clientY: number, zoomDelta: number): void;
};

function shouldIgnoreBoardPointerDown(target: HTMLElement): boolean {
  return Boolean(
    target.closest('[data-workflow-node-id]')
    || target.closest('[data-workflow-node-menu]')
    || target.closest('[data-node-browser]')
    || target.closest('[data-open-node-browser]')
    || target.closest(
      'button, input, select, textarea, a, [role="button"], [contenteditable="true"]',
    )
    || target.closest('[data-remove-edge]')
    || target.closest('[data-workflow-settings-panel]'),
  );
}

function shouldIgnoreNodePointerDown(target: HTMLElement): boolean {
  return Boolean(
    target.closest('[data-node-action]')
    || target.closest('[data-workflow-node-aux-port]'),
  );
}

function getHoveredEdgeIdFromTarget(target: Element): string | null {
  const hoveredRemoveButton = target.closest<HTMLElement>('[data-remove-edge]');
  const hoveredEdgeHit = target.closest<SVGPathElement>('[data-workflow-edge-hit-id]');
  return hoveredRemoveButton?.dataset.removeEdge ?? hoveredEdgeHit?.dataset.workflowEdgeHitId ?? null;
}

export function registerWorkflowDesignerPointerInteractions(params: {
  addEdge: (
    sourceId: string,
    targetId: string,
    options?: {
      sourcePort?: AgentAuxiliaryPortId;
      targetPort?: AgentAuxiliaryPortId;
    },
  ) => void;
  beginConnection: (sourceId: string, pointerId: number, clientX: number, clientY: number) => void;
  canvas: CanvasElements;
  closeNodeContextMenu: () => void;
  getConnectionDraft: () => ConnectionDraft | null;
  getDragState: () => DragState | null;
  getHoveredEdgeId: () => string | null;
  getHoveredTarget: (clientX: number, clientY: number, sourceId: string) => WorkflowConnectionHoverTarget | null;
  getNode: (nodeId: string) => WorkflowNode | undefined;
  getNodeElement: (nodeId: string) => HTMLElement | null;
  getPanState: () => PanState | null;
  getPointFromClient: (clientX: number, clientY: number) => Point;
  getSelectedNodeId: () => string | null;
  getSettingsNodeId: () => string | null;
  hasOpenContextMenu: () => boolean;
  isValidConnection: (
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ) => boolean;
  openInsertBrowser: (sourceId: string, clientX: number, clientY: number) => void;
  openNodeContextMenu: (nodeId: string, clientX: number, clientY: number) => void;
  renderCanvas: () => void;
  renderEdges: () => void;
  renderNodes: () => void;
  renderSettingsPanel: () => void;
  shouldKeepSettingsOpenOnNodeSelect: () => boolean;
  setConnectionDraft: (nextState: ConnectionDraft | null) => void;
  setDragState: (nextState: DragState | null) => void;
  setHoveredEdgeId: (nextState: string | null) => void;
  setPanState: (nextState: PanState | null) => void;
  setSelectedNodeId: (nextState: string | null) => void;
  setSettingsNodeId: (nextState: string | null) => void;
  shouldOpenInsertBrowser: (clientX: number, clientY: number) => boolean;
  updateNodePosition: (nodeId: string, position: Point) => void;
  viewportController: PointerViewportController;
}): void {
  const {
    addEdge,
    beginConnection,
    canvas,
    closeNodeContextMenu,
    getConnectionDraft,
    getDragState,
    getHoveredEdgeId,
    getHoveredTarget,
    getNode,
    getNodeElement,
    getPanState,
    getPointFromClient,
    getSelectedNodeId,
    getSettingsNodeId,
    hasOpenContextMenu,
    isValidConnection,
    openInsertBrowser,
    openNodeContextMenu,
    renderCanvas,
    renderEdges,
    renderNodes,
    renderSettingsPanel,
    shouldKeepSettingsOpenOnNodeSelect,
    setConnectionDraft,
    setDragState,
    setHoveredEdgeId,
    setPanState,
    setSelectedNodeId,
    setSettingsNodeId,
    shouldOpenInsertBrowser,
    updateNodePosition,
    viewportController,
  } = params;

  function stopDragging(pointerId: number): void {
    const dragState = getDragState();
    if (!dragState || dragState.pointerId !== pointerId) {
      return;
    }

    const nodeElement = getNodeElement(dragState.nodeId);
    if (nodeElement) {
      nodeElement.classList.remove('is-dragging');
      if (nodeElement.hasPointerCapture(pointerId)) {
        nodeElement.releasePointerCapture(pointerId);
      }
    }

    setDragState(null);
    renderCanvas();
  }

  function stopPanning(pointerId: number): void {
    const panState = getPanState();
    if (!panState || panState.pointerId !== pointerId) {
      return;
    }

    const didMove = panState.didMove;
    setPanState(null);
    canvas.board.classList.remove('is-panning');
    if (canvas.board.hasPointerCapture(pointerId)) {
      canvas.board.releasePointerCapture(pointerId);
    }

    if (!didMove) {
      if (getSelectedNodeId()) {
        setSelectedNodeId(null);
        setSettingsNodeId(null);
        renderCanvas();
        renderSettingsPanel();
        return;
      }

      if (getSettingsNodeId()) {
        setSettingsNodeId(null);
        renderSettingsPanel();
      }
    }
  }

  function stopConnecting(pointerId: number, clientX: number, clientY: number): void {
    const connectionDraft = getConnectionDraft();
    if (!connectionDraft || connectionDraft.pointerId !== pointerId) {
      return;
    }

    const targetId = connectionDraft.hoveredTargetId;
    const targetPort = connectionDraft.hoveredTargetPort;
    const sourceId = connectionDraft.sourceId;
    setConnectionDraft(null);

    if (targetId && isValidConnection(sourceId, targetId, targetPort)) {
      addEdge(sourceId, targetId, targetPort ? { sourcePort: targetPort, targetPort } : undefined);
      return;
    }

    if (shouldOpenInsertBrowser(clientX, clientY)) {
      openInsertBrowser(sourceId, clientX, clientY);
      renderCanvas();
      return;
    }

    renderCanvas();
  }

  canvas.board.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) {
      return;
    }

    const target = event.target as HTMLElement;
    if (shouldIgnoreBoardPointerDown(target)) {
      return;
    }

    setPanState({
      didMove: false,
      lastClientX: event.clientX,
      lastClientY: event.clientY,
      pointerId: event.pointerId,
    });
    canvas.board.classList.add('is-panning');
    canvas.board.setPointerCapture(event.pointerId);
  });

  canvas.nodeLayer.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) {
      return;
    }

    const target = event.target as HTMLElement;
    if (shouldIgnoreNodePointerDown(target)) {
      return;
    }
    if (hasOpenContextMenu()) {
      closeNodeContextMenu();
    }

    const connector = target.closest<HTMLElement>('[data-workflow-node-connector]');
    if (connector?.dataset.workflowNodeConnector) {
      beginConnection(
        connector.dataset.workflowNodeConnector,
        event.pointerId,
        event.clientX,
        event.clientY,
      );
      event.preventDefault();
      return;
    }

    const nodeElement = target.closest<HTMLElement>('[data-workflow-node-id]');
    const nodeId = nodeElement?.dataset.workflowNodeId;
    if (!nodeElement || !nodeId) {
      return;
    }

    const node = getNode(nodeId);
    if (!node) {
      return;
    }

    if (getSelectedNodeId() !== nodeId) {
      setSelectedNodeId(nodeId);
      if (shouldKeepSettingsOpenOnNodeSelect()) {
        setSettingsNodeId(nodeId);
      } else {
        setSettingsNodeId(null);
      }
      renderNodes();
      renderSettingsPanel();
    }

    if (getSettingsNodeId() && !shouldKeepSettingsOpenOnNodeSelect()) {
      setSettingsNodeId(null);
      renderSettingsPanel();
    }

    const activeNodeElement = getNodeElement(nodeId);
    if (!activeNodeElement) {
      return;
    }

    const cursorPoint = viewportController.screenToWorld(event.clientX, event.clientY);

    setDragState({
      nodeId,
      offsetX: cursorPoint.x - node.position.x,
      offsetY: cursorPoint.y - node.position.y,
      pointerId: event.pointerId,
    });

    activeNodeElement.classList.add('is-dragging');
    activeNodeElement.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  canvas.nodeLayer.addEventListener('contextmenu', (event) => {
    const target = event.target as HTMLElement;
    const nodeElement = target.closest<HTMLElement>('[data-workflow-node-id]');
    const nodeId = nodeElement?.dataset.workflowNodeId;
    if (!nodeId) {
      return;
    }

    event.preventDefault();
    openNodeContextMenu(nodeId, event.clientX, event.clientY);
  });

  canvas.board.addEventListener('pointermove', (event) => {
    if (getDragState() || getConnectionDraft()) {
      if (getHoveredEdgeId()) {
        setHoveredEdgeId(null);
        renderEdges();
      }
      return;
    }

    const nextHoveredEdgeId = getHoveredEdgeIdFromTarget(event.target as Element);
    if (getHoveredEdgeId() === nextHoveredEdgeId) {
      return;
    }

    setHoveredEdgeId(nextHoveredEdgeId);
    renderEdges();
  });

  canvas.board.addEventListener('pointerleave', () => {
    if (!getHoveredEdgeId()) {
      return;
    }

    setHoveredEdgeId(null);
    renderEdges();
  });

  window.addEventListener('pointermove', (event) => {
    const panState = getPanState();
    if (panState && event.pointerId === panState.pointerId) {
      const deltaX = event.clientX - panState.lastClientX;
      const deltaY = event.clientY - panState.lastClientY;
      if (Math.abs(deltaX) > 0 || Math.abs(deltaY) > 0) {
        setPanState({
          ...panState,
          didMove: true,
          lastClientX: event.clientX,
          lastClientY: event.clientY,
        });
        viewportController.panBy(deltaX, deltaY);
      }
      return;
    }

    const connectionDraft = getConnectionDraft();
    if (connectionDraft && event.pointerId === connectionDraft.pointerId) {
      const pointerPoint = getPointFromClient(event.clientX, event.clientY);
      const nextHoveredTarget = getHoveredTarget(
        event.clientX,
        event.clientY,
        connectionDraft.sourceId,
      );
      const didHoverTargetChange =
        connectionDraft.hoveredTargetId !== nextHoveredTarget?.nodeId ||
        connectionDraft.hoveredTargetPort !== nextHoveredTarget?.targetPort ||
        connectionDraft.hoveredTargetSide !== nextHoveredTarget?.side;
      setConnectionDraft({
        ...connectionDraft,
        hoveredTargetId: nextHoveredTarget?.nodeId ?? null,
        hoveredTargetPort: nextHoveredTarget?.targetPort ?? null,
        hoveredTargetSide: nextHoveredTarget?.side ?? null,
        pointerX: pointerPoint.x,
        pointerY: pointerPoint.y,
      });
      renderNodes();
      if (didHoverTargetChange) {
        renderEdges();
        return;
      }
      renderEdges();
      return;
    }

    const dragState = getDragState();
    if (!dragState || event.pointerId !== dragState.pointerId) {
      return;
    }

    const cursorPoint = viewportController.screenToWorld(event.clientX, event.clientY);

    updateNodePosition(dragState.nodeId, {
      x: cursorPoint.x - dragState.offsetX,
      y: cursorPoint.y - dragState.offsetY,
    });
  });

  window.addEventListener('pointerup', (event) => {
    stopConnecting(event.pointerId, event.clientX, event.clientY);
    stopDragging(event.pointerId);
    stopPanning(event.pointerId);
  });

  window.addEventListener('pointercancel', (event) => {
    stopConnecting(event.pointerId, event.clientX, event.clientY);
    stopDragging(event.pointerId);
    stopPanning(event.pointerId);
  });

  canvas.board.addEventListener('wheel', (event) => {
    if (!event.ctrlKey && !event.metaKey) {
      return;
    }

    const zoomDelta = event.deltaY < 0 ? 0.08 : -0.08;
    viewportController.zoomAt(event.clientX, event.clientY, zoomDelta);
    event.preventDefault();
  }, { passive: false });
}
