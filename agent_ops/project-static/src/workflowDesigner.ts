import {
  getBrowserElements,
  getCanvasElements,
  getExecutionElements,
} from './workflowDesigner/dom';
import {
  clampNodePosition,
  getNodeRenderHeight,
  getNodeRenderWidth,
  getSuggestedNodePosition,
} from './workflowDesigner/geometry';
import {
  canNodeEmitConnections,
  isValidConnection as validateConnection,
} from './workflowDesigner/interactions/connections';
import {
  registerWorkflowDesignerPointerInteractions,
  type ConnectionDraft,
  type DragState,
  type PanState,
} from './workflowDesigner/interactions/pointerController';
import { registerWorkflowDesignerUiBindings } from './workflowDesigner/interactions/uiBindings';
import {
  getDefaultBrowserView,
} from './workflowDesigner/panels/browserState';
import { createWorkflowDesignerBrowserController } from './workflowDesigner/panels/browserController';
import {
  renderSettingsIdentitySection,
  renderNodeSettingsFieldsMarkup,
  renderSettingsOverviewSection,
} from './workflowDesigner/panels/settingsPanel';
import { createWorkflowDesignerSettingsController } from './workflowDesigner/panels/settingsController';
import {
  getAvailableInputPaths,
} from './workflowDesigner/panels/settingsAssist';
import {
  getFieldOptionsWithCurrentValue,
} from './workflowDesigner/presenters/nodePresentation';
import { buildNodeRegistry, getAvailablePaletteSections } from './workflowDesigner/registry/nodeRegistry';
import { normalizeWorkflowDefinition, serializeWorkflowDefinition } from './workflowDesigner/schema/workflowSchema';
import { createWorkflowDesignerGraphController } from './workflowDesigner/state/graphController';
import { createGraphStore } from './workflowDesigner/state/graphStore';
import { createWorkflowDesignerCanvasController } from './workflowDesigner/state/canvasController';
import { createWorkflowDesignerExecutionController } from './workflowDesigner/state/executionController';
import { createWorkflowDesignerRenderController } from './workflowDesigner/state/renderController';
import { createWorkflowDesignerSelectionController } from './workflowDesigner/state/selectionController';
import type {
  AgentAuxiliaryPortId,
  WorkflowCatalogPayload,
  WorkflowConnection,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeTemplateField,
  WorkflowPersistedDefinition,
} from './workflowDesigner/types';
import {
  cloneValue,
  createId,
  formatKindLabel,
  isTemplateFieldVisible,
  parseJsonScript,
} from './workflowDesigner/utils';
import { createViewportController } from './workflowDesigner/viewport/controller';

const NODE_CONTEXT_MENU_WIDTH = 224;
const NODE_CONTEXT_MENU_HEIGHT = 142;
const NODE_CONTEXT_MENU_MARGIN = 12;
const NODE_CONTEXT_MENU_OFFSET_X = 10;
const NODE_CONTEXT_MENU_OFFSET_Y = 6;
const TERMINAL_RUN_STATUSES = new Set(['succeeded', 'failed']);

function isTerminalRunStatus(status: string): boolean {
  return TERMINAL_RUN_STATUSES.has(status);
}

function parsePersistedDefinition(
  definitionInput: HTMLInputElement | HTMLTextAreaElement,
): WorkflowPersistedDefinition | null {
  if (!definitionInput.value.trim()) {
    return null;
  }

  try {
    return JSON.parse(definitionInput.value) as WorkflowPersistedDefinition;
  } catch (error) {
    console.error(error);
    return null;
  }
}

function getRealAppId(definition: WorkflowNodeDefinition | undefined): string {
  const appId = definition?.app_id?.trim();
  if (!appId || appId === 'builtins') {
    return '';
  }

  return appId;
}

function getRealAppLabel(definition: WorkflowNodeDefinition | undefined): string {
  if (!definition) {
    return '';
  }

  return getRealAppId(definition) ? definition.app_label?.trim() ?? '' : '';
}

function createWorkflowNode(
  board: HTMLElement,
  definition: WorkflowDefinition,
  nodeDefinition: WorkflowNodeDefinition,
  selectedNodeId: string | null,
  overridePosition?: { x: number; y: number },
): WorkflowNode {
  return {
    config: cloneValue(nodeDefinition.config ?? {}),
    id: createId('node'),
    kind: nodeDefinition.kind,
    label: nodeDefinition.label,
    position: clampNodePosition(
      board,
      overridePosition ?? getSuggestedNodePosition(board, definition, selectedNodeId, nodeDefinition),
      getNodeRenderHeight(nodeDefinition),
      getNodeRenderWidth(nodeDefinition),
    ),
    type: nodeDefinition.type,
    typeVersion: nodeDefinition.typeVersion,
  };
}

function getNodeTargetOptions(currentNode: WorkflowNode, definition: WorkflowDefinition): Array<{ label: string; value: string }> {
  return definition.nodes
    .filter((node) => node.id !== currentNode.id)
    .map((node) => ({
      label: node.label || formatKindLabel(node.kind) || node.type,
      value: node.id,
    }));
}

export function initWorkflowDesigner(): void {
  const root = document.querySelector<HTMLElement>('[data-workflow-designer]');
  if (!root) {
    return;
  }

  const browserElements = getBrowserElements(root);
  const canvasElements = getCanvasElements(root);
  if (!browserElements || !canvasElements) {
    return;
  }
  const browser = browserElements;
  const canvas = canvasElements;
  const execution = getExecutionElements(root);
  const workflowRunUrl = root.dataset.workflowRunUrl ?? '';
  const workflowNodeRunUrlTemplate = root.dataset.workflowNodeRunUrlTemplate ?? '';
  const csrfToken = root.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]')?.value ?? '';

  const fallbackDefinition = parseJsonScript<WorkflowPersistedDefinition>('workflow-definition-data', {
    edges: [],
    nodes: [],
  });
  const persistedDefinition = parsePersistedDefinition(canvas.definitionInput) ?? fallbackDefinition;
  const graphStore = createGraphStore({
    definition: normalizeWorkflowDefinition(persistedDefinition),
    persist(definition) {
      canvas.definitionInput.value = JSON.stringify(serializeWorkflowDefinition(definition));
    },
  });
  const workflowDefinition = graphStore.definition;
  const workflowCatalog = parseJsonScript<WorkflowCatalogPayload>('workflow-catalog-data', {
    definitions: [],
    groups: [],
    presentation: {
      chrome: {
        browser: {
          aria_label: 'Node browser',
          close_label: 'Close node browser',
          default_title: 'Add node',
          search_label: 'Search nodes',
        },
        canvas: {
          controls_aria_label: 'Canvas controls',
          empty_state: {
            action_aria_label: 'Add the first workflow step',
            action_caption: 'Choose a trigger to start the workflow',
            action_label: 'Add first step',
          },
          zoom: {
            fit: 'Fit',
            zoom_in: 'Zoom in',
            zoom_out: 'Zoom out',
          },
        },
        execution_panel: {
          aria_label: 'Execution preview',
          context_label: 'Context',
          description: 'Test the selected node here, or use the toolbar to run the full workflow.',
          empty: 'Run the selected node to inspect output, trace, and context here.',
          output_label: 'Output',
          title: 'Run preview',
          trace_label: 'Trace',
        },
        settings_panel: {
          aria_label: 'Node settings',
          close_label: 'Close node settings',
          title: 'Node settings',
        },
        toolbar: {
          add_node: 'Add node',
          back_label: 'Workflow',
          run_workflow: 'Run workflow',
          settings: 'Settings',
        },
      },
      node_selection: {
        app_actions: {
          action_meta: 'Action nodes',
          empty: 'No matching apps',
          search_placeholder: 'Search nodes...',
          title: 'Action in an app',
        },
        app_details: {
          default_title: 'Node details',
          empty: 'No nodes available for this app',
          sections: {
            actions: 'Actions',
            triggers: 'Triggers',
          },
        },
        category_details: {
          empty_template: 'No matching {group} nodes',
          fallback_empty: 'No matching nodes',
          search_placeholder: 'Search nodes...',
        },
        common: {
          add_description: 'Choose the next step to add to this workflow.',
          connect_description: 'Choose the next step to connect from here.',
          default_empty: 'No matching nodes',
          default_search_placeholder: 'Search nodes, apps, or actions',
          default_title: 'Add node',
        },
        insert: {
          model_provider: {
            description: 'Choose a provider-backed model node. Each one includes curated presets and an optional custom override.',
            empty: 'No matching model providers',
            search_placeholder: 'Search model providers',
            title: 'Attach model provider',
          },
          tool: {
            description: 'Choose any tool or integration node to attach to this agent.',
            empty: 'No matching tools',
            search_placeholder: 'Search tools',
            title: 'Attach tool',
          },
        },
        next_step_root: {
          empty: 'No matching node categories',
          items: {
            app_action: {
              description: 'Do something in an app or service like Elasticsearch or Prometheus.',
              label: 'Action in an app',
            },
          },
          search_placeholder: 'Search nodes...',
          title: 'What happens next?',
        },
        trigger_apps: {
          empty: 'No matching apps',
          search_placeholder: 'Search nodes...',
          title: 'On app event',
          trigger_meta: 'Trigger nodes',
        },
        trigger_root: {
          additional: {
            description: 'Triggers start your workflow. Workflows can have multiple triggers.',
            label: 'Add another trigger',
          },
          empty: 'No matching triggers',
          initial: {
            description: 'A trigger is a step that starts your workflow',
            title: 'What triggers this workflow?',
          },
          items: {
            app_event: {
              description: 'Start the workflow from an event in one of your apps.',
            },
            manual: {
              label: 'Trigger manually',
            },
            schedule: {
              label: 'On a schedule',
            },
          },
          search_placeholder: 'Search nodes...',
        },
      },
      execution: {
        default_status: {
          badge_class: 'text-bg-secondary',
          label: 'Idle',
        },
        messages: {
          execution_failed: 'Execution failed.',
          poll_timeout: 'Workflow run polling timed out.',
          status_fetch_failed: 'Unable to fetch run status.',
        },
        result_labels: {
          node_run: 'Node run',
          workflow_run: 'Workflow run',
        },
        run_button: {
          idle: 'Run node',
          running: 'Running node',
        },
        running_status: {
          node: 'Running node',
          workflow: 'Running workflow',
        },
        statuses: {
          failed: {
            badge_class: 'text-bg-danger',
            label: 'Failed',
          },
          pending: {
            badge_class: 'text-bg-secondary',
            label: 'Queued',
          },
          running: {
            badge_class: 'text-bg-primary',
            label: 'Running',
          },
          succeeded: {
            badge_class: 'text-bg-success',
            label: 'Completed',
          },
        },
      },
      settings: {
        controls: {
          expression_hint: 'Use template syntax like {{ trigger.payload.ticket_id }} or {{ llm.response.text }}.',
          mode_expression: 'Expression',
          mode_static: 'Static',
          mode_suffix: 'mode',
          select_placeholder: 'Select',
        },
        empty: 'No editable settings for this node yet.',
        groups: {
          advanced: {
            description: 'Provider, routing, and runtime controls for this node.',
            title: 'Other settings',
          },
          identity: {
            description: 'Rename the node so the graph reads clearly.',
            fields: {
              node_name: 'Node name',
            },
            title: 'Identity',
          },
          input: {
            description: 'Choose Static or Expression for each input, then map trigger payload and earlier node outputs.',
            title: 'Pass data in',
          },
          overview: {
            description: 'Keep the graph readable and make the node’s role obvious at a glance.',
            fields: {
              node_id: 'Node id',
              type: 'Type',
            },
            title: 'Node overview',
          },
          result: {
            description: 'Choose where this node should read or write workflow context values.',
            title: 'Save result',
          },
        },
      },
    },
    sections: [],
  });
  const workflowConnections = parseJsonScript<WorkflowConnection[]>('workflow-connections-data', []);
  const nodeRegistry = buildNodeRegistry(
    workflowCatalog.definitions,
    workflowConnections,
    workflowCatalog.sections,
  );
  let renderCanvas = (): void => {};
  let renderCanvasHud = (): void => {};
  let renderEdges = (): void => {};
  let renderNodeContextMenu = (): void => {};
  let renderNodes = (): void => {};
  const viewportController = createViewportController({
    board: canvas.board,
    surface: canvas.surface,
    viewport: {
      x: workflowDefinition.viewport?.x ?? 0,
      y: workflowDefinition.viewport?.y ?? 0,
      zoom: workflowDefinition.viewport?.zoom ?? 1,
    },
    onChange(viewport) {
      graphStore.setViewport(viewport);
      graphStore.commit();
      renderEdges();
      renderNodeContextMenu();
      renderCanvasHud();
    },
  });

  let dragState: DragState | null = null;
  let panState: PanState | null = null;
  let connectionDraft: ConnectionDraft | null = null;
  let hoveredEdgeId: string | null = null;

  function syncDefinitionInput(): void {
    graphStore.commit();
  }

  function getNode(nodeId: string | null): WorkflowNode | undefined {
    return graphStore.getNode(nodeId);
  }

  function getInitialExecutionNodeId(nodeId: string | null): string | null {
    if (nodeId) {
      return nodeId;
    }

    const triggerNode = workflowDefinition.nodes.find((node) => node.kind === 'trigger');
    if (triggerNode) {
      return triggerNode.id;
    }

    return workflowDefinition.nodes[0]?.id ?? null;
  }

  function buildExecutionRequestBody(inputData: Record<string, unknown>): string {
    return JSON.stringify({
      definition: serializeWorkflowDefinition(workflowDefinition),
      input_data: inputData,
    });
  }

  function getNodeRunUrl(nodeId: string): string {
    return workflowNodeRunUrlTemplate.replace('__node_id__', encodeURIComponent(nodeId));
  }

  function isEmptyWorkflow(): boolean {
    return workflowDefinition.nodes.length === 0;
  }

  function isValidConnection(
    sourceId: string,
    targetId: string,
    targetPort?: AgentAuxiliaryPortId | null,
  ): boolean {
    return validateConnection({
      getNode,
      getNodeDefinition,
      sourceId,
      targetId,
      targetPort,
      workflowDefinition,
    });
  }

  function getNodeDefinition(node: WorkflowNode | undefined): WorkflowNodeDefinition | undefined {
    if (!node) {
      return undefined;
    }

    return nodeRegistry.definitionMap.get(node.type);
  }

  function getVisibleTargetFields(
    node: WorkflowNode,
    nodeDefinition: WorkflowNodeDefinition | undefined,
  ): WorkflowNodeTemplateField[] {
    if (!nodeDefinition) {
      return [];
    }

    return nodeDefinition.fields.filter(
      (field) => field.type === 'node_target' && isTemplateFieldVisible(node, field),
    );
  }

  function isTextEntryTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) {
      return false;
    }

    return Boolean(
      target.closest(
        'input:not([type="button"]):not([type="checkbox"]):not([type="radio"]), textarea, select, [contenteditable="true"]',
      ),
    );
  }

  function renderSettingsPanel(): void {
    const settingsNode = getNode(getSettingsNodeId());
    const nodeDefinition = getNodeDefinition(settingsNode);
    if (!settingsNode || !nodeDefinition) {
      canvas.settingsPanel.hidden = true;
      canvas.settingsFields.innerHTML = '';
      renderExecutionNodeAction();
      return;
    }

    const activeSettingsNode = settingsNode;
    const activeNodeDefinition = nodeDefinition;
    const availableInputPaths = getAvailableInputPaths({
      executionInputData: {},
      getNode,
      nodeId: activeSettingsNode.id,
      workflowDefinition,
    });
    const fieldMarkup = renderNodeSettingsFieldsMarkup({
      availableInputPaths,
      getFieldOptions: (field) => getFieldOptionsWithCurrentValue(activeSettingsNode, field),
      getNodeTargetOptions: () => getNodeTargetOptions(activeSettingsNode, workflowDefinition),
      node: activeSettingsNode,
      nodeDefinition: activeNodeDefinition,
      presentation: workflowCatalog.presentation.settings,
    });

    const description = nodeDefinition.description || nodeDefinition.label;
    canvas.settingsPanel.hidden = false;
    canvas.settingsTitle.textContent = settingsNode.label || nodeDefinition.label;
    canvas.settingsDescription.textContent = description;
    canvas.settingsFields.innerHTML = `
      ${renderSettingsOverviewSection({
        nodeDefinitionLabel: nodeDefinition.label,
        nodeId: settingsNode.id,
        presentation: workflowCatalog.presentation.settings,
      })}
      ${renderSettingsIdentitySection({
        nodeId: settingsNode.id,
        nodeLabel: settingsNode.label,
        presentation: workflowCatalog.presentation.settings,
      })}
      ${fieldMarkup || `<div class="workflow-editor-settings-empty">${workflowCatalog.presentation.settings.empty}</div>`}
    `;
    renderExecutionNodeAction();
  }

  const {
    getHoveredTarget,
    getNodeContextMenuPosition,
    getNodeElement,
    getPointFromClient,
    repositionGraph,
    updateNodePosition,
  } = createWorkflowDesignerCanvasController({
    board: canvas.board,
    contextMenuHeight: NODE_CONTEXT_MENU_HEIGHT,
    contextMenuMargin: NODE_CONTEXT_MENU_MARGIN,
    contextMenuOffsetX: NODE_CONTEXT_MENU_OFFSET_X,
    contextMenuOffsetY: NODE_CONTEXT_MENU_OFFSET_Y,
    contextMenuWidth: NODE_CONTEXT_MENU_WIDTH,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getWorkflowDefinition: () => workflowDefinition,
    isValidConnection,
    nodeLayer: canvas.nodeLayer,
    renderEdges: () => renderEdges(),
    syncDefinitionInput,
    viewportController,
  });

  function cancelConnection(): void {
    connectionDraft = null;
    renderCanvas();
  }

  const {
    cleanupDeletedNode,
    clearContextMenuState,
    closeNodeContextMenu,
    closeNodeSettings,
    getContextMenuState,
    getSelectedNodeId,
    getSettingsNodeId,
    hasOpenContextMenu,
    openNodeContextMenu,
    openNodeSettings,
    setSelectedNodeId,
    setSettingsNodeId,
  } = createWorkflowDesignerSelectionController({
    getContextMenuPosition: getNodeContextMenuPosition,
    getNode: (nodeId) => getNode(nodeId ?? null),
    renderCanvas,
    renderNodeContextMenu,
    renderSettingsPanel,
  });

  const {
    executeDesignerRun,
    getActiveExecutionNodeId,
    getExecutionActiveNodeIds,
    getExecutionFailedNodeIds,
    getExecutionSucceededNodeId,
    getIsExecutionPending,
    renderExecutionNodeAction,
  } = createWorkflowDesignerExecutionController({
    buildExecutionRequestBody,
    csrfToken,
    execution,
    executionPresentation: workflowCatalog.presentation.execution,
    getInitialExecutionNodeId,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getSelectedNodeId,
    getSettingsNodeId,
    isTerminalRunStatus,
    onExecutionStateChange: () => {
      renderCanvas();
      renderSettingsPanel();
    },
    openNodeSettings,
  });

  ({
    renderCanvas,
    renderCanvasHud,
    renderEdges,
    renderNodeContextMenu,
    renderNodes,
  } = createWorkflowDesignerRenderController({
    canvas,
    clearContextMenuState,
    getActiveExecutionNodeId,
    getAppLabel: getRealAppLabel,
    getConnectionDraft: () => connectionDraft,
    getContextMenuState,
    getExecutionActiveNodeIds,
    getExecutionFailedNodeIds,
    getExecutionSucceededNodeId,
    getHoveredEdgeId: () => hoveredEdgeId,
    getIsExecutionPending,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getNodeDefinition,
    getSelectedNodeId,
    getViewportZoom: () => viewportController.getViewport().zoom,
    getWorkflowDefinition: () => workflowDefinition,
    isDragActive: () => Boolean(dragState),
    isEmptyWorkflow,
    isValidConnection,
    viewportWorldToScreen: viewportController.worldToScreen,
  }));

  const {
    closeBrowser,
    getInsertDraft,
    getIsBrowserOpen,
    goBackBrowserView,
    navigateBrowser,
    openAuxiliaryInsertBrowser,
    openBrowser,
    openInsertBrowser,
    renderBrowser,
    setSearchQuery,
    showEmptyWorkflowBrowser,
  } = createWorkflowDesignerBrowserController({
    board: canvas.board,
    browser,
    clearContextMenuState,
    clearSettingsNodeId: () => setSettingsNodeId(null),
    catalogSections: workflowCatalog.sections,
    definitions: nodeRegistry.definitions,
    getAvailableSections: () => getAvailablePaletteSections(nodeRegistry, workflowDefinition),
    getIsEmptyWorkflow: isEmptyWorkflow,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getWorkflowDefinition: () => workflowDefinition,
    initialIsOpen: workflowDefinition.nodes.length === 0,
    initialView: getDefaultBrowserView(workflowDefinition.nodes.length === 0),
    openNodeSettings,
    groups: workflowCatalog.groups,
    presentation: workflowCatalog.presentation.node_selection,
    renderCanvas,
    renderNodeContextMenu,
    renderSettingsPanel,
    screenToWorld: viewportController.screenToWorld,
    setSelectedNodeId: (nodeId) => setSelectedNodeId(nodeId),
  });

  const {
    addEdge,
    deleteNode,
    removeEdge,
    syncNodeTargetEdges,
  } = createWorkflowDesignerGraphController({
    createEdgeId: () => createId('edge'),
    getNode: (nodeId) => getNode(nodeId ?? null),
    getNodeDefinition,
    getWorkflowDefinition: () => workflowDefinition,
    getVisibleTargetFields,
    graphStore,
    isValidConnection,
    onClearHoveredEdge: () => {
      hoveredEdgeId = null;
    },
    onDeleteNodeStateCleanup: (nodeId) => {
      cleanupDeletedNode(nodeId);
      if (connectionDraft?.sourceId === nodeId) {
        connectionDraft = null;
      }
      hoveredEdgeId = null;
    },
    renderBrowser,
    renderCanvas,
    renderSettingsPanel,
    showEmptyWorkflowBrowser,
    syncDefinitionInput,
  });

  function shouldOpenInsertBrowser(clientX: number, clientY: number): boolean {
    const target = document.elementFromPoint(clientX, clientY) as HTMLElement | null;
    if (!target) {
      return false;
    }

    if (
      target.closest('[data-node-browser]') ||
      target.closest('[data-open-node-browser]') ||
      target.closest('[data-workflow-settings-panel]') ||
      target.closest('[data-workflow-node-id]')
    ) {
      return false;
    }

    return Boolean(target.closest('[data-workflow-board]'));
  }

  function addNode(nodeType: string): void {
    const nodeDefinition = nodeRegistry.definitionMap.get(nodeType);
    if (!nodeDefinition) {
      return;
    }

    const pendingInsert = getInsertDraft();
    const newNode = createWorkflowNode(
      canvas.board,
      workflowDefinition,
      nodeDefinition,
      getSelectedNodeId(),
      pendingInsert?.position,
    );
    graphStore.addNode(newNode);
    setSelectedNodeId(newNode.id);
    syncDefinitionInput();
    closeBrowser();
    if (pendingInsert?.sourceId) {
      addEdge(pendingInsert.sourceId, newNode.id);
      setSettingsNodeId(newNode.id);
    } else if (pendingInsert?.targetId && pendingInsert.targetPort) {
      addEdge(newNode.id, pendingInsert.targetId, {
        sourcePort: pendingInsert.targetPort,
        targetPort: pendingInsert.targetPort,
      });
      setSettingsNodeId(newNode.id);
    }
    renderCanvas();
    renderBrowser();
    renderSettingsPanel();
  }

  const {
    applyNodeSettingSuggestion,
    updateSelectedNodeField,
    updateSelectedNodeFieldMode,
    updateSelectedNodeLabel,
  } = createWorkflowDesignerSettingsController({
    canvas,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getNodeDefinition,
    getSettingsNodeId,
    renderCanvas,
    renderSettingsPanel,
    syncDefinitionInput,
    syncNodeTargetEdges,
  });

  function beginConnection(sourceId: string, pointerId: number, clientX: number, clientY: number): void {
    const sourceNode = getNode(sourceId);
    const sourceDefinition = getNodeDefinition(sourceNode);
    if (!sourceNode || !canNodeEmitConnections(sourceNode, workflowDefinition.edges, sourceDefinition)) {
      return;
    }

    const pointerPoint = getPointFromClient(clientX, clientY);
    setSelectedNodeId(sourceId);
    hoveredEdgeId = null;
    connectionDraft = {
      hoveredTargetId: null,
      hoveredTargetPort: null,
      hoveredTargetSide: null,
      pointerId,
      pointerX: pointerPoint.x,
      pointerY: pointerPoint.y,
      sourceId,
    };
    renderCanvas();
  }

  registerWorkflowDesignerPointerInteractions({
    addEdge,
    beginConnection,
    canvas,
    closeNodeContextMenu,
    getConnectionDraft: () => connectionDraft,
    getDragState: () => dragState,
    getHoveredEdgeId: () => hoveredEdgeId,
    getHoveredTarget,
    getNode: (nodeId) => getNode(nodeId),
    getNodeElement,
    getPanState: () => panState,
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
    setConnectionDraft: (nextState) => {
      connectionDraft = nextState;
    },
    setDragState: (nextState) => {
      dragState = nextState;
    },
    setHoveredEdgeId: (nextState) => {
      hoveredEdgeId = nextState;
    },
    setPanState: (nextState) => {
      panState = nextState;
    },
    setSelectedNodeId,
    setSettingsNodeId,
    shouldOpenInsertBrowser,
    updateNodePosition,
    viewportController,
  });

  registerWorkflowDesignerUiBindings({
    addNode,
    applyNodeSettingSuggestion,
    browser,
    canvas,
    cancelConnection,
    closeBrowser,
    closeNodeContextMenu,
    closeNodeSettings,
    deleteNode,
    getConnectionDraftActive: () => Boolean(connectionDraft),
    getContextMenuNodeId: () => getContextMenuState()?.nodeId ?? null,
    getIsBrowserOpen,
    getSelectedNodeId,
    getSettingsNodeId,
    goBackBrowserView,
    isTextEntryTarget,
    navigateBrowser,
    openAuxiliaryInsertBrowser,
    openBrowser,
    openNodeSettings,
    removeEdge,
    renderBrowser,
    repositionGraph,
    root,
    runNode: (nodeId) => {
      void executeDesignerRun(getNodeRunUrl(nodeId), { nodeId });
    },
    runSelectedNode: () => {
      const settingsNodeId = getSettingsNodeId();
      if (!settingsNodeId) {
        return;
      }
      void executeDesignerRun(getNodeRunUrl(settingsNodeId), { nodeId: settingsNodeId });
    },
    runWorkflow: () => {
      void executeDesignerRun(workflowRunUrl);
    },
    setSearchQuery,
    updateSelectedNodeField,
    updateSelectedNodeFieldMode,
    updateSelectedNodeLabel,
    zoomByStep: (direction) => {
      viewportController.zoomByStep(direction);
    },
  });

  syncDefinitionInput();
  renderCanvas();
  renderBrowser();
  renderSettingsPanel();
}
