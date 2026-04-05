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
  renderNodeConnectionSection,
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
import {
  createWorkflowDesignerExecutionController,
  type DesignerRunResponse,
  type DesignerRunStep,
} from './workflowDesigner/state/executionController';
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
  escapeHtml,
  formatKindLabel,
  isTemplateFieldVisible,
  parseJsonScript,
  supportsNodeDisabledState,
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

function createWebhookPathId(): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
    const randomValue = Math.floor(Math.random() * 16);
    const nextValue = character === 'x' ? randomValue : (randomValue & 0x3) | 0x8;
    return nextValue.toString(16);
  });
}

function createWorkflowNode(
  board: HTMLElement,
  definition: WorkflowDefinition,
  nodeDefinition: WorkflowNodeDefinition,
  selectedNodeId: string | null,
  overridePosition?: { x: number; y: number },
): WorkflowNode {
  const config = cloneValue(nodeDefinition.config ?? {}) as Record<string, unknown>;
  if (nodeDefinition.type === 'core.webhook_trigger') {
    const existingPath = typeof config.path === 'string' ? config.path.trim() : '';
    if (!existingPath) {
      config.path = createWebhookPathId();
    }
  }

  return {
    config,
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
  const workflowConnectionAddUrl = root.dataset.workflowConnectionAddUrl ?? '';
  const workflowConnectionsUrl = root.dataset.workflowConnectionsUrl ?? '';
  const workflowSaveUrl = root.dataset.workflowSaveUrl ?? '';
  const workflowRunUrl = root.dataset.workflowRunUrl ?? '';
  const workflowWebhookUrl = root.dataset.workflowWebhookUrl ?? '';
  const workflowNodeRunUrlTemplate = root.dataset.workflowNodeRunUrlTemplate ?? '';
  const csrfToken = root.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]')?.value ?? '';
  const autosaveStatus = root.querySelector<HTMLElement>('[data-workflow-save-status]');

  root.addEventListener('submit', (event) => {
    event.preventDefault();
  });

  function setAutosaveStatus(state: 'error' | 'saved' | 'saving', message?: string): void {
    if (!autosaveStatus) {
      return;
    }

    autosaveStatus.dataset.state = state;
    autosaveStatus.textContent = message ?? (
      state === 'saving'
        ? 'Saving changes...'
        : state === 'error'
          ? 'Autosave failed'
          : 'All changes saved'
    );
  }

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
          input_description: 'Latest results from previous nodes on the main path.',
          input_title: 'Input',
          output_description: 'Latest current-node result plus the full execution inspector.',
          output_title: 'Output',
          parameters_tab: 'Parameters',
          settings_empty: 'No additional settings for this node.',
          settings_tab: 'Settings',
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
            description: 'Triggers start your workflow. Add another trigger when the workflow should start in more than one way.',
            label: 'Add trigger',
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
        inspector: {
          overview: {
            active_nodes: 'Active nodes',
            failed_nodes: 'Failed nodes',
            idle_value: 'None',
            last_completed_node: 'Last completed',
            mode: 'Mode',
            selected_node: 'Selected node',
            skipped_nodes: 'Skipped nodes',
            step_count: 'Step count',
            trigger_mode: 'Trigger mode',
            workflow_version: 'Workflow version',
          },
          steps: {
            empty: 'No completed steps yet.',
            next_node_label: 'Next node',
            result_label: 'Result',
            title: 'Step details',
          },
          tabs: {
            context: 'Context',
            input: 'Input',
            output: 'Output',
            overview: 'Overview',
            steps: 'Steps',
            trace: 'Trace',
          },
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
          required_badge: 'Required',
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
  const workflowNodeKindsByType = workflowCatalog.definitions.reduce<Record<string, string>>(
    (accumulator, definition) => {
      accumulator[definition.type] = definition.kind;
      return accumulator;
    },
    {},
  );
  const workflowNodeConfigByType = workflowCatalog.definitions.reduce<Record<string, Record<string, unknown>>>(
    (accumulator, definition) => {
      accumulator[definition.type] = definition.config && typeof definition.config === 'object'
        ? { ...definition.config }
        : {};
      return accumulator;
    },
    {},
  );
  const workflowConnectionSlotKeysByType = workflowCatalog.definitions.reduce<Record<string, string[]>>(
    (accumulator, definition) => {
      accumulator[definition.type] = (definition.connection_slots ?? []).map((slot) => slot.key);
      return accumulator;
    },
    {},
  );
  const fallbackDefinition = parseJsonScript<WorkflowPersistedDefinition>('workflow-definition-data', {
    definition_version: 2,
    edges: [],
    nodes: [],
  });
  const persistedDefinition = parsePersistedDefinition(canvas.definitionInput) ?? fallbackDefinition;
  const persistedAutosaveRevision = typeof (persistedDefinition as { autosave_revision?: unknown }).autosave_revision === 'number'
    && Number.isFinite((persistedDefinition as { autosave_revision?: number }).autosave_revision)
    && (persistedDefinition as { autosave_revision?: number }).autosave_revision! >= 0
    ? (persistedDefinition as { autosave_revision?: number }).autosave_revision!
    : 0;
  const graphStore = createGraphStore({
    definition: normalizeWorkflowDefinition(persistedDefinition, {
      configByType: workflowNodeConfigByType,
      connectionSlotKeysByType: workflowConnectionSlotKeysByType,
      kindByType: workflowNodeKindsByType,
    }),
    persist(definition) {
      canvas.definitionInput.value = JSON.stringify(
        serializeWorkflowDefinition(definition, {
          connectionSlotKeysByType: workflowConnectionSlotKeysByType,
        }),
      );
    },
  });
  const workflowDefinition = graphStore.definition;
  const autosaveController = createAutosaveController();
  const autosaveRevisionStorageKey = `workflow-designer-autosave-revision:${workflowSaveUrl || window.location.pathname}`;
  let workflowConnections = parseJsonScript<WorkflowConnection[]>('workflow-connections-data', []);
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
      autosaveController.schedule();
      renderEdges();
      renderNodeContextMenu();
      renderCanvasHud();
    },
  });

  let dragState: DragState | null = null;
  let panState: PanState | null = null;
  let connectionDraft: ConnectionDraft | null = null;
  let hoveredEdgeId: string | null = null;

  function buildConnectionEditorUrl(
    rawUrl: string,
    options?: { defaultConnectionType?: string },
  ): string {
    const url = new URL(rawUrl, window.location.origin);
    url.searchParams.set('popup', '1');
    url.searchParams.set('return_url', window.location.href);
    if (options?.defaultConnectionType && !url.searchParams.get('connection_type')) {
      url.searchParams.set('connection_type', options.defaultConnectionType);
    }
    return url.toString();
  }

  function openConnectionPopup(rawUrl: string, options?: { defaultConnectionType?: string }): void {
    const popupUrl = buildConnectionEditorUrl(rawUrl, options);
    window.open(
      popupUrl,
      'workflowConnectionEditor',
      'popup=yes,width=980,height=860,resizable=yes,scrollbars=yes',
    );
  }

  async function refreshWorkflowConnections(): Promise<void> {
    if (!workflowConnectionsUrl) {
      return;
    }

    try {
      const response = await fetch(workflowConnectionsUrl, {
        headers: {
          Accept: 'application/json',
        },
        credentials: 'same-origin',
      });
      if (!response.ok) {
        throw new Error(`Failed to refresh workflow connections (${response.status})`);
      }
      const payload = await response.json() as { connections?: WorkflowConnection[] };
      workflowConnections = Array.isArray(payload.connections) ? payload.connections : [];
      renderSettingsPanel();
    } catch (error) {
      console.error(error);
    }
  }

  function syncDefinitionInput(): void {
    graphStore.commit();
    autosaveController.schedule();
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
      definition: serializeWorkflowDefinition(workflowDefinition, {
        connectionSlotKeysByType: workflowConnectionSlotKeysByType,
      }),
      input_data: inputData,
    });
  }

  function buildAutosaveRequestBody(revision: number): string {
    return JSON.stringify({
      definition: serializeWorkflowDefinition(workflowDefinition, {
        connectionSlotKeysByType: workflowConnectionSlotKeysByType,
      }),
      revision,
    });
  }

  async function getAutosaveErrorMessage(response: Response): Promise<string> {
    let payload: { detail?: unknown } | null = null;

    try {
      payload = await response.json() as { detail?: unknown };
    } catch (error) {
      console.error(error);
    }

    if (typeof payload?.detail === 'string' && payload.detail.trim()) {
      return payload.detail;
    }

    return `Autosave failed (${response.status}).`;
  }

  function createAutosaveController(): {
    flush: () => void;
    markReady: () => void;
    schedule: () => void;
  } {
    if (!workflowSaveUrl) {
      if (autosaveStatus) {
        autosaveStatus.hidden = true;
      }

      return {
        flush() {},
        markReady() {},
        schedule() {},
      };
    }

    let isReady = false;
    let debounceHandle: number | null = null;
    let isSaving = false;
    let shouldSaveAgain = false;
    let issuedRevision = (() => {
      try {
        const storedValue = window.sessionStorage.getItem(autosaveRevisionStorageKey);
        const parsedValue = storedValue ? Number.parseInt(storedValue, 10) : 0;
        if (Number.isFinite(parsedValue) && parsedValue >= 0) {
          return Math.max(parsedValue, persistedAutosaveRevision);
        }
        return persistedAutosaveRevision;
      } catch (error) {
        console.error(error);
        return persistedAutosaveRevision;
      }
    })();
    let draftRevision = issuedRevision;
    let savedRevision = issuedRevision;

    function persistIssuedRevision(): void {
      try {
        window.sessionStorage.setItem(autosaveRevisionStorageKey, String(issuedRevision));
      } catch (error) {
        console.error(error);
      }
    }

    function clearDebounceTimer(): void {
      if (debounceHandle === null) {
        return;
      }

      window.clearTimeout(debounceHandle);
      debounceHandle = null;
    }

    async function saveNow(): Promise<void> {
      if (draftRevision <= savedRevision) {
        setAutosaveStatus('saved');
        return;
      }

      if (isSaving) {
        shouldSaveAgain = true;
        return;
      }

      isSaving = true;
      shouldSaveAgain = false;
      setAutosaveStatus('saving');
      const revisionToSave = draftRevision;

      try {
        const response = await fetch(workflowSaveUrl, {
          body: buildAutosaveRequestBody(revisionToSave),
          credentials: 'same-origin',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          method: 'POST',
        });

        if (!response.ok) {
          throw new Error(await getAutosaveErrorMessage(response));
        }

        const payload = await response.json() as { detail?: unknown; stale?: unknown };
        if (payload.stale === true) {
          throw new Error(typeof payload.detail === 'string' && payload.detail.trim()
            ? payload.detail
            : 'Autosave conflict detected.');
        }

        savedRevision = Math.max(savedRevision, revisionToSave);
        setAutosaveStatus(savedRevision >= draftRevision ? 'saved' : 'saving');
      } catch (error) {
        console.error(error);
        const message = error instanceof Error && error.message
          ? error.message
          : 'Autosave failed';
        setAutosaveStatus('error', message);
      } finally {
        isSaving = false;

        if (shouldSaveAgain || savedRevision < draftRevision) {
          shouldSaveAgain = false;
          debounceHandle = window.setTimeout(() => {
            debounceHandle = null;
            void saveNow();
          }, 250);
        }
      }
    }

    return {
      flush() {
        if (!isReady || draftRevision <= savedRevision) {
          return;
        }

        clearDebounceTimer();
        const revisionToSave = draftRevision;
        void fetch(workflowSaveUrl, {
          body: buildAutosaveRequestBody(revisionToSave),
          credentials: 'same-origin',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          keepalive: true,
          method: 'POST',
        })
          .then((response) => {
            if (response.ok) {
              savedRevision = Math.max(savedRevision, revisionToSave);
            }
          })
          .catch((error) => {
            console.error(error);
          });
      },
      markReady() {
        isReady = true;
        setAutosaveStatus('saved');
      },
      schedule() {
        if (!isReady) {
          return;
        }

        issuedRevision += 1;
        draftRevision = issuedRevision;
        persistIssuedRevision();
        setAutosaveStatus('saving');

        clearDebounceTimer();

        debounceHandle = window.setTimeout(() => {
          debounceHandle = null;
          void saveNow();
        }, 500);
      },
    };
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

  let selectedSettingsTab: 'parameters' | 'settings' = 'parameters';
  let selectedSettingsTabNodeId: string | null = null;

  function renderSettingsPanel(): void {
    const settingsNode = getNode(getSettingsNodeId());
    const nodeDefinition = getNodeDefinition(settingsNode);
    const settingsInput = canvas.settingsPanel.querySelector<HTMLElement>('[data-workflow-settings-input]');
    const settingsCurrentOutput = canvas.settingsPanel.querySelector<HTMLElement>('[data-workflow-settings-current-output]');
    if (!settingsNode || !nodeDefinition) {
      selectedSettingsTabNodeId = null;
      canvas.settingsPanel.hidden = true;
      canvas.settingsFields.innerHTML = '';
      if (settingsInput) {
        settingsInput.innerHTML = '';
      }
      if (settingsCurrentOutput) {
        settingsCurrentOutput.innerHTML = '';
      }
      renderExecutionNodeAction();
      return;
    }

    if (selectedSettingsTabNodeId !== settingsNode.id) {
      selectedSettingsTab = 'parameters';
      selectedSettingsTabNodeId = settingsNode.id;
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
      webhookUrl: workflowWebhookUrl,
    });
    const connectionMarkup = renderNodeConnectionSection({
      connectionCreateUrl: workflowConnectionAddUrl,
      connections: workflowConnections,
      node: activeSettingsNode,
      nodeDefinition: activeNodeDefinition,
      presentation: workflowCatalog.presentation.settings,
    });
    const lastExecutionPayload = getLastExecutionPayload();
    const inputPaneMarkup = renderSettingsInputPaneMarkup({
      getNode: (nodeId) => getNode(nodeId ?? null),
      getNodeDefinition,
      node: activeSettingsNode,
      payload: lastExecutionPayload,
      presentation: workflowCatalog.presentation,
      workflowDefinition,
    });
    const parameterTabMarkup =
      [
        fieldMarkup,
        connectionMarkup,
      ]
        .filter((markup) => markup && markup.trim().length > 0)
        .join('')
      || `<div class="workflow-editor-settings-empty">${workflowCatalog.presentation.settings.empty}</div>`;
    const settingsTabMarkup =
      [
        renderSettingsOverviewSection({
          nodeDefinitionLabel: nodeDefinition.label,
          nodeId: settingsNode.id,
          presentation: workflowCatalog.presentation.settings,
        }),
        renderSettingsIdentitySection({
          nodeId: settingsNode.id,
          nodeLabel: settingsNode.label,
          presentation: workflowCatalog.presentation.settings,
        }),
      ]
        .filter((sectionMarkup) => sectionMarkup.length > 0)
        .join('')
      || `<div class="workflow-editor-settings-empty">${escapeHtml(
        workflowCatalog.presentation.chrome.settings_panel.settings_empty,
      )}</div>`;

    const description = nodeDefinition.description || nodeDefinition.label;
    canvas.settingsPanel.hidden = false;
    canvas.settingsTitle.textContent = settingsNode.label || nodeDefinition.label;
    canvas.settingsDescription.textContent = description;
    canvas.settingsFields.innerHTML = `
      <div class="workflow-editor-settings-tab-list" role="tablist" aria-label="Node editor tabs">
        <button
          type="button"
          class="workflow-editor-settings-tab${selectedSettingsTab === 'parameters' ? ' is-active' : ''}"
          data-workflow-settings-tab="parameters"
          role="tab"
          aria-selected="${selectedSettingsTab === 'parameters' ? 'true' : 'false'}"
        >
          ${escapeHtml(workflowCatalog.presentation.chrome.settings_panel.parameters_tab)}
        </button>
        <button
          type="button"
          class="workflow-editor-settings-tab${selectedSettingsTab === 'settings' ? ' is-active' : ''}"
          data-workflow-settings-tab="settings"
          role="tab"
          aria-selected="${selectedSettingsTab === 'settings' ? 'true' : 'false'}"
        >
          ${escapeHtml(workflowCatalog.presentation.chrome.settings_panel.settings_tab)}
        </button>
      </div>
      <div class="workflow-editor-settings-tab-panel">
        ${selectedSettingsTab === 'parameters' ? parameterTabMarkup : settingsTabMarkup}
      </div>
    `;
    if (settingsInput) {
      settingsInput.innerHTML = inputPaneMarkup;
    }
    if (settingsCurrentOutput) {
      settingsCurrentOutput.innerHTML = '';
    }
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

  window.addEventListener('message', (event) => {
    if (event.origin !== window.location.origin || typeof event.data !== 'object' || event.data === null) {
      return;
    }
    const message = event.data as { type?: string };
    if (message.type === 'workflow-connection-updated') {
      void refreshWorkflowConnections();
    }
  });

  const {
    executeDesignerRun,
    getActiveExecutionNodeId,
    getExecutionActiveNodeIds,
    getExecutionCompletedNodeIds,
    getExecutionCurrentNodeId,
    getExecutionFailedNodeIds,
    getLastExecutionPayload,
    getExecutionSkippedNodeIds,
    getIsExecutionPending,
    renderExecutionNodeAction,
    selectExecutionStep,
    selectExecutionTab,
    syncExecutionSelectionToNode,
  } = createWorkflowDesignerExecutionController({
    buildExecutionRequestBody,
    csrfToken,
    execution,
    executionPresentation: workflowCatalog.presentation.execution,
    getWorkflowHasWebhookTriggers: () => workflowDefinition.nodes.some(
      (node: WorkflowNode) => node.kind === 'trigger' && node.type.toLowerCase().includes('webhook'),
    ),
    getInitialExecutionNodeId,
    getNode: (nodeId) => getNode(nodeId ?? null),
    getSelectedNodeId,
    isTerminalRunStatus,
    onExecutionStateChange: ({ focusNodeId }) => {
      if (focusNodeId) {
        setSelectedNode(focusNodeId);
      }
      renderCanvas();
      renderSettingsPanel();
    },
  });

  function setSelectedNode(nodeId: string | null): void {
    setSelectedNodeId(nodeId);
    syncExecutionSelectionToNode(nodeId);
  }

  function openWorkflowNodeSettings(nodeId: string): void {
    openNodeSettings(nodeId);
    syncExecutionSelectionToNode(nodeId);
  }

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
    getExecutionCompletedNodeIds,
    getExecutionCurrentNodeId,
    getExecutionFailedNodeIds,
    getExecutionSkippedNodeIds,
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
    openNodeSettings: openWorkflowNodeSettings,
    groups: workflowCatalog.groups,
    presentation: workflowCatalog.presentation.node_selection,
    renderCanvas,
    renderNodeContextMenu,
    renderSettingsPanel,
    screenToWorld: viewportController.screenToWorld,
    setSelectedNodeId: (nodeId) => setSelectedNode(nodeId),
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
    setSelectedNode(newNode.id);
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

  function toggleNodeDisabled(nodeId: string): void {
    const node = getNode(nodeId);
    if (!node || !supportsNodeDisabledState(node)) {
      return;
    }

    node.disabled = !node.disabled;
    syncDefinitionInput();
    renderCanvas();
    renderSettingsPanel();
  }

  const {
    addSelectedNodeCollectionItem,
    applyNodeSettingSuggestion,
    removeSelectedNodeCollectionItem,
    updateSelectedNodeField,
    updateSelectedNodeFieldPath,
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
    setSelectedNode(sourceId);
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
    shouldKeepSettingsOpenOnNodeSelect: () => Boolean(getSettingsNodeId()),
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
    setSelectedNodeId: setSelectedNode,
    setSettingsNodeId,
    shouldOpenInsertBrowser,
    updateNodePosition,
    viewportController,
  });

  registerWorkflowDesignerUiBindings({
    addNode,
    addSelectedNodeCollectionItem,
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
    openConnectionPopup,
    openNodeSettings: openWorkflowNodeSettings,
    removeEdge,
    removeSelectedNodeCollectionItem,
    renderBrowser,
    repositionGraph,
    root,
    runNode: (nodeId) => {
      void executeDesignerRun(getNodeRunUrl(nodeId), { nodeId });
    },
    runSelectedNode: () => {
      const selectedNodeId = getSelectedNodeId();
      if (!selectedNodeId) {
        return;
      }
      void executeDesignerRun(getNodeRunUrl(selectedNodeId), { nodeId: selectedNodeId });
    },
    runWorkflow: () => {
      void executeDesignerRun(workflowRunUrl);
    },
    selectSettingsTab: (tab) => {
      if (selectedSettingsTab === tab) {
        return;
      }
      selectedSettingsTab = tab;
      renderSettingsPanel();
    },
    selectExecutionStep,
    selectExecutionTab,
    setSearchQuery,
    toggleNodeDisabled,
    updateSelectedNodeField,
    updateSelectedNodeFieldPath,
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
  autosaveController.markReady();
  window.addEventListener('pagehide', () => {
    autosaveController.flush();
  });
}

function parseDesignerJsonValue<T>(value: string | null): T | null {
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value) as T;
  } catch (error) {
    console.error(error);
    return null;
  }
}

function formatDesignerJsonValue(value: unknown, fallback = '{}'): string {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }

  if (typeof value === 'string') {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch (error) {
    console.error(error);
    return fallback;
  }
}

function buildStepLookup(payload: DesignerRunResponse | null): Map<string, DesignerRunStep> {
  const steps = parseDesignerJsonValue<DesignerRunStep[]>(payload?.run.steps_json ?? null) ?? [];

  return new Map(
    steps
      .filter(
        (step): step is DesignerRunStep & { node_id: string } =>
          typeof step.node_id === 'string' && step.node_id.length > 0,
      )
      .map((step) => [step.node_id, step]),
  );
}

function getMainPathIncomingSourceIds(workflowDefinition: WorkflowDefinition, nodeId: string): string[] {
  return Array.from(
    new Set(
      workflowDefinition.edges
        .filter(
          (edge) =>
            edge.target === nodeId
            && edge.targetPort !== 'ai_languageModel'
            && edge.targetPort !== 'ai_tool',
        )
        .map((edge) => edge.source),
    ),
  );
}

function renderSettingsInputPaneMarkup(params: {
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getNodeDefinition: (node: WorkflowNode | undefined) => WorkflowNodeDefinition | undefined;
  node: WorkflowNode;
  payload: DesignerRunResponse | null;
  presentation: WorkflowCatalogPayload['presentation'];
  workflowDefinition: WorkflowDefinition;
}): string {
  const { getNode, getNodeDefinition, node, payload, presentation, workflowDefinition } = params;
  const settingsExecutionGroup = presentation.settings.groups.execution ?? {
    title: 'Execution data',
    description: 'Inspect upstream results and the latest result for this node.',
  };
  const fields = settingsExecutionGroup.fields ?? {};
  const incomingSourceIds = getMainPathIncomingSourceIds(workflowDefinition, node.id);

  if (!payload) {
    return renderSettingsPaneEmptyState({
      action: 'previous',
      caption: 'Execute previous nodes to view input data.',
      title: 'No input data',
    });
  }

  const stepByNodeId = buildStepLookup(payload);
  const runMeta = [
    payload.mode.startsWith('node') ? 'Latest node run' : 'Latest workflow run',
    `Run #${payload.run.id}`,
    presentation.execution.statuses[payload.run.status]?.label ?? payload.run.status,
  ].join(' · ');

  if (incomingSourceIds.length === 0) {
    return renderSettingsPaneEmptyState({
      caption: fields.no_previous ?? 'This node has no previous nodes on the main path.',
      title: 'No input data',
    });
  }

  return `
    <div class="workflow-editor-settings-results-stack">
      <div class="workflow-editor-settings-help">${escapeHtml(runMeta)}</div>
      <div class="workflow-editor-settings-results-list">
        ${incomingSourceIds
          .map((sourceId) =>
            renderSettingsResultCard({
              emptyLabel: fields.no_result ?? 'No result in the latest run.',
              getNode,
              getNodeDefinition,
              nodeId: sourceId,
              step: stepByNodeId.get(sourceId) ?? null,
            }),
          )
          .join('')}
      </div>
    </div>
  `;
}

function renderSettingsPaneEmptyState(params: {
  action?: 'previous' | 'selected';
  caption: string;
  title: string;
}): string {
  const buttonMarkup = (() => {
    if (params.action === 'previous') {
      return `
        <button type="button" class="btn btn-danger btn-sm" data-workflow-run-previous-nodes>
          <i class="mdi mdi-play"></i>
          <span class="ms-1">Execute previous nodes</span>
        </button>
      `;
    }

    if (params.action === 'selected') {
      return `
        <button type="button" class="btn btn-danger btn-sm" data-workflow-run-selected-node>
          <i class="mdi mdi-play"></i>
          <span class="ms-1">Run node</span>
        </button>
      `;
    }

    return '';
  })();

  return `
    <div class="workflow-editor-pane-empty-state">
      <div class="workflow-editor-pane-empty-icon" aria-hidden="true">
        <i class="mdi mdi-arrow-right"></i>
      </div>
      <div class="workflow-editor-pane-empty-title">${escapeHtml(params.title)}</div>
      ${buttonMarkup}
      <div class="workflow-editor-pane-empty-caption">${escapeHtml(params.caption)}</div>
    </div>
  `;
}

function renderSettingsResultCard(params: {
  emptyLabel: string;
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getNodeDefinition: (node: WorkflowNode | undefined) => WorkflowNodeDefinition | undefined;
  nodeId: string;
  step: DesignerRunStep | null;
}): string {
  const node = params.getNode(params.nodeId);
  const definition = params.getNodeDefinition(node);
  const title = node?.label || params.step?.label || params.nodeId;
  const metaParts = [
    definition ? formatKindLabel(definition.kind) : '',
    definition?.label ?? '',
    params.nodeId,
  ].filter((part) => part);

  return `
    <div class="workflow-editor-settings-result-card">
      <div class="workflow-editor-settings-result-head">
        <div class="workflow-editor-settings-result-title">${escapeHtml(title)}</div>
        <div class="workflow-editor-settings-result-meta">${escapeHtml(metaParts.join(' · '))}</div>
      </div>
      ${
        params.step
          ? `<pre class="workflow-json-preview mb-0">${escapeHtml(formatDesignerJsonValue(params.step.result ?? {}, '{}'))}</pre>`
          : `<div class="workflow-editor-settings-empty">${escapeHtml(params.emptyLabel)}</div>`
      }
    </div>
  `;
}
