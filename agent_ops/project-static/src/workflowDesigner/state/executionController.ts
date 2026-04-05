import type { ExecutionElements } from '../dom';
import { isWebhookTriggerDefinition } from '../registry/nodeSemantics';
import type { WorkflowExecutionPresentation, WorkflowNode } from '../types';
import { escapeHtml, formatKindLabel, isNodeDisabled } from '../utils';

export type DesignerRunResponse = {
  message: string;
  mode: string;
  node?: {
    id: string;
    kind: string;
    label: string;
    type: string;
  };
  poll_url?: string;
  run: {
    active_node_ids: string[];
    badge_class: string;
    context_json: string | null;
    error: string;
    failed_node_ids: string[];
    id: number;
    input_json: string | null;
    last_completed_node_id: string | null;
    output_json: string | null;
    skipped_node_ids: string[];
    status: string;
    step_count: number;
    steps_json: string | null;
    trigger_mode: string;
    workflow_version: number;
  };
};

export type ExecutionInspectorTab = 'overview' | 'output' | 'input' | 'context' | 'steps' | 'trace';

export type DesignerRunStep = {
  kind?: string;
  label?: string;
  node_id?: string;
  result?: unknown;
  type?: string;
};

export function createWorkflowDesignerExecutionController(params: {
  buildExecutionRequestBody: (inputData: Record<string, unknown>) => string;
  csrfToken: string;
  execution: ExecutionElements | null;
  executionPresentation: WorkflowExecutionPresentation;
  getNodeDefinition: (nodeId: string | null | undefined) => { capabilities?: string[] } | undefined;
  getWorkflowHasWebhookTriggers: () => boolean;
  getInitialExecutionNodeId: (nodeId: string | null) => string | null;
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getSelectedNodeId: () => string | null;
  isTerminalRunStatus: (status: string) => boolean;
  onExecutionStateChange: (state: {
    focusNodeId: string | null;
  }) => void;
}): {
  executeDesignerRun: (
    url: string,
    options?: {
      nodeId?: string | null;
    },
  ) => Promise<void>;
  getActiveExecutionNodeId: () => string | null;
  getExecutionActiveNodeIds: () => string[];
  getExecutionCompletedNodeIds: () => string[];
  getExecutionCurrentNodeId: () => string | null;
  getExecutionFailedNodeIds: () => string[];
  getLastExecutionPayload: () => DesignerRunResponse | null;
  getExecutionSkippedNodeIds: () => string[];
  getIsExecutionPending: () => boolean;
  renderExecutionNodeAction: () => void;
  selectExecutionStep: (stepIndex: number) => void;
  selectExecutionTab: (tab: ExecutionInspectorTab) => void;
  syncExecutionSelectionToNode: (nodeId: string | null) => void;
} {
  const {
    buildExecutionRequestBody,
    csrfToken,
    execution,
    executionPresentation,
    getNodeDefinition,
    getWorkflowHasWebhookTriggers,
    getInitialExecutionNodeId,
    getNode,
    getSelectedNodeId,
    isTerminalRunStatus,
    onExecutionStateChange,
  } = params;

  let isExecutionPending = false;
  let activeExecutionNodeId: string | null = null;
  let executionActiveNodeIds: string[] = [];
  let executionCompletedNodeIds: string[] = [];
  let executionCurrentNodeId: string | null = null;
  let executionFailedNodeIds: string[] = [];
  let executionSkippedNodeIds: string[] = [];
  let selectedExecutionTab: ExecutionInspectorTab = 'overview';
  let selectedExecutionStepIndex = 0;
  let lastExecutionPayload: DesignerRunResponse | null = null;

  function isWebhookListenMode(payload: DesignerRunResponse | null): boolean {
    return payload?.mode === 'node_listen' || payload?.mode === 'workflow_listen';
  }

  function parseJsonValue<T>(value: string | null): T | null {
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

  function formatJsonValue(value: unknown, fallback: string): string {
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

  function setExecutionStatus(label: string, badgeClass = 'text-bg-secondary'): void {
    if (!execution) {
      return;
    }

    execution.status.textContent = label;
    execution.status.className = `badge ${badgeClass}`;
  }

  function clearExecutionError(): void {
    if (!execution) {
      return;
    }

    execution.error.hidden = true;
    execution.error.textContent = '';
  }

  function showExecutionError(message: string): void {
    if (!execution) {
      return;
    }

    execution.error.hidden = false;
    execution.error.textContent = message;
  }

  function parseExecutionInput(): Record<string, unknown> | null {
    if (!execution) {
      return {};
    }

    clearExecutionError();
    return {};
  }

  function getNodeLabel(nodeId: string | null | undefined): string {
    if (!nodeId) {
      return executionPresentation.inspector.overview.idle_value;
    }

    const node = getNode(nodeId);
    return node?.label || nodeId;
  }

  function getNodeListLabel(nodeIds: string[]): string {
    if (nodeIds.length === 0) {
      return executionPresentation.inspector.overview.idle_value;
    }

    return nodeIds.map((nodeId) => getNodeLabel(nodeId)).join(', ');
  }

  function getExecutionSteps(payload: DesignerRunResponse | null): DesignerRunStep[] {
    if (!payload) {
      return [];
    }

    const parsedSteps = parseJsonValue<DesignerRunStep[]>(payload.run.steps_json);
    return Array.isArray(parsedSteps) ? parsedSteps : [];
  }

  function getLatestExecutionStepIndexForNode(
    payload: DesignerRunResponse | null,
    nodeId: string | null,
  ): number {
    if (!payload || !nodeId) {
      return -1;
    }

    const steps = getExecutionSteps(payload);
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      if (steps[index]?.node_id === nodeId) {
        return index;
      }
    }

    return -1;
  }

  function getCompletedNodeIds(payload: DesignerRunResponse): string[] {
    const completedNodeIds: string[] = [];
    const seenNodeIds = new Set<string>();
    const failedNodeIds = new Set(payload.run.failed_node_ids ?? []);
    const activeNodeIds = new Set(payload.run.active_node_ids ?? []);

    getExecutionSteps(payload).forEach((step) => {
      const nodeId = step.node_id;
      if (!nodeId || seenNodeIds.has(nodeId) || failedNodeIds.has(nodeId) || activeNodeIds.has(nodeId)) {
        return;
      }

      seenNodeIds.add(nodeId);
      completedNodeIds.push(nodeId);
    });

    return completedNodeIds;
  }

  function getExecutionFocusNodeId(payload: DesignerRunResponse | null): string | null {
    if (!payload) {
      return null;
    }

    if ((payload.run.active_node_ids ?? []).length > 0) {
      return payload.run.active_node_ids[0] ?? null;
    }

    if ((payload.run.failed_node_ids ?? []).length > 0) {
      return payload.run.failed_node_ids[0] ?? null;
    }

    return payload.run.last_completed_node_id ?? payload.node?.id ?? null;
  }

  function resolveDefaultExecutionTab(payload: DesignerRunResponse): ExecutionInspectorTab {
    if (parseJsonValue(payload.run.output_json) !== null) {
      return 'output';
    }

    const parsedSteps = parseJsonValue<DesignerRunStep[]>(payload.run.steps_json);
    if (Array.isArray(parsedSteps) && parsedSteps.length > 0) {
      return 'steps';
    }

    return 'overview';
  }

  function renderExecutionInspector(): void {
    if (!execution || !lastExecutionPayload) {
      return;
    }

    const payload = lastExecutionPayload;
    const parsedInput = parseJsonValue<Record<string, unknown>>(payload.run.input_json) ?? {};
    const parsedOutput = parseJsonValue(payload.run.output_json);
    const parsedContext = parseJsonValue<Record<string, unknown>>(payload.run.context_json) ?? {};
    const parsedSteps = parseJsonValue<DesignerRunStep[]>(payload.run.steps_json);
    const steps = Array.isArray(parsedSteps) ? parsedSteps : [];
    const tabs = executionPresentation.inspector.tabs;
    const orderedTabs = (
      ['output', 'context', 'input', 'overview', 'steps', 'trace'] as ExecutionInspectorTab[]
    ).filter((tabKey) => Object.prototype.hasOwnProperty.call(tabs, tabKey));
    const overviewLabels = executionPresentation.inspector.overview;
    const selectedStep = steps[selectedExecutionStepIndex] ?? null;

    const stepDetailMarkup = selectedStep
      ? `
          ${
            steps.length > 1
              ? `
                <div class="workflow-editor-execution-group">
                  <div class="text-secondary mb-1">Step</div>
                  <div class="workflow-editor-execution-stat-value">${escapeHtml(`${selectedExecutionStepIndex + 1} of ${steps.length}`)}</div>
                </div>
              `
              : ''
          }
          <pre class="workflow-json-preview mb-0">${escapeHtml(formatJsonValue(selectedStep.result ?? {}, '{}'))}</pre>
        `
      : `<div class="workflow-editor-settings-empty">${escapeHtml(executionPresentation.inspector.steps.empty)}</div>`;

    const panes: Record<ExecutionInspectorTab, string> = {
      overview: `
        <div class="workflow-editor-execution-overview-grid">
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.mode)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(payload.mode)}</div>
          </div>
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.selected_node)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(payload.node?.label || overviewLabels.idle_value)}</div>
          </div>
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.trigger_mode)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(payload.run.trigger_mode || overviewLabels.idle_value)}</div>
          </div>
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.workflow_version)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(`v${payload.run.workflow_version}`)}</div>
          </div>
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.step_count)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(String(payload.run.step_count))}</div>
          </div>
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.last_completed_node)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(getNodeLabel(payload.run.last_completed_node_id))}</div>
          </div>
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.active_nodes)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(getNodeListLabel(payload.run.active_node_ids ?? []))}</div>
          </div>
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.failed_nodes)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(getNodeListLabel(payload.run.failed_node_ids ?? []))}</div>
          </div>
          <div class="workflow-editor-execution-stat">
            <div class="workflow-editor-execution-stat-label">${escapeHtml(overviewLabels.skipped_nodes)}</div>
            <div class="workflow-editor-execution-stat-value">${escapeHtml(getNodeListLabel(payload.run.skipped_node_ids ?? []))}</div>
          </div>
        </div>
      `,
      output: `
        <div class="workflow-editor-execution-group">
          <div class="text-secondary mb-1">${escapeHtml(tabs.output)}</div>
          <pre class="workflow-json-preview mb-0">${escapeHtml(formatJsonValue(parsedOutput ?? {}, '{}'))}</pre>
        </div>
      `,
      input: `
        <div class="workflow-editor-execution-group">
          <div class="text-secondary mb-1">${escapeHtml(tabs.input)}</div>
          <pre class="workflow-json-preview mb-0">${escapeHtml(formatJsonValue(parsedInput, '{}'))}</pre>
        </div>
      `,
      context: `
        <div class="workflow-editor-execution-group">
          <div class="text-secondary mb-1">${escapeHtml(tabs.context)}</div>
          <pre class="workflow-json-preview mb-0">${escapeHtml(formatJsonValue(parsedContext, '{}'))}</pre>
        </div>
      `,
      steps: `
        <div class="workflow-editor-execution-step-detail">
          ${stepDetailMarkup}
        </div>
      `,
      trace: `
        <div class="workflow-editor-execution-group">
          <div class="text-secondary mb-1">${escapeHtml(tabs.trace)}</div>
          <pre class="workflow-json-preview mb-0">${escapeHtml(payload.run.steps_json ?? '[]')}</pre>
        </div>
      `,
    };

    execution.resultBody.innerHTML = `
      <div class="workflow-editor-execution-tab-list" role="tablist" aria-label="Execution inspector">
        ${orderedTabs
          .map(
            (tabKey) => `
              <button
                type="button"
                class="workflow-editor-execution-tab${selectedExecutionTab === tabKey ? ' is-active' : ''}"
                data-workflow-execution-tab="${tabKey}"
                role="tab"
                aria-selected="${selectedExecutionTab === tabKey ? 'true' : 'false'}"
              >
                ${escapeHtml(tabs[tabKey])}
              </button>
            `,
          )
          .join('')}
      </div>
      <div class="workflow-editor-execution-pane">
        ${panes[selectedExecutionTab]}
      </div>
    `;
  }

  function selectExecutionTab(tab: ExecutionInspectorTab): void {
    if (!lastExecutionPayload) {
      return;
    }

    selectedExecutionTab = tab;
    renderExecutionInspector();
  }

  function selectExecutionStep(stepIndex: number): void {
    if (!lastExecutionPayload) {
      return;
    }

    const parsedSteps = parseJsonValue<DesignerRunStep[]>(lastExecutionPayload.run.steps_json);
    if (!Array.isArray(parsedSteps) || stepIndex < 0 || stepIndex >= parsedSteps.length) {
      return;
    }

    selectedExecutionStepIndex = stepIndex;
    selectedExecutionTab = 'steps';
    renderExecutionInspector();
  }

  function syncExecutionSelectionToNode(nodeId: string | null): void {
    if (!lastExecutionPayload || !nodeId) {
      return;
    }

    const stepIndex = getLatestExecutionStepIndexForNode(lastExecutionPayload, nodeId);
    if (stepIndex >= 0) {
      selectedExecutionStepIndex = stepIndex;
      selectedExecutionTab = 'steps';
      renderExecutionInspector();
      return;
    }

    if (lastExecutionPayload.run.last_completed_node_id === nodeId) {
      const hasOutput = parseJsonValue(lastExecutionPayload.run.output_json) !== null;
      selectedExecutionTab = hasOutput ? 'output' : 'overview';
      renderExecutionInspector();
    }
  }

  function renderExecutionResult(payload: DesignerRunResponse): void {
    if (!execution) {
      return;
    }

    lastExecutionPayload = payload;
    const statusPresentation = isWebhookListenMode(payload) && payload.run.status === 'pending'
      ? {
          badge_class: executionPresentation.statuses.pending?.badge_class ?? 'text-bg-secondary',
          label: 'Listening',
        }
      : executionPresentation.statuses[payload.run.status] ?? {
      badge_class: executionPresentation.default_status.badge_class,
      label: payload.run.status,
      };
    executionActiveNodeIds = payload.run.active_node_ids ?? [];
    executionCompletedNodeIds = getCompletedNodeIds(payload);
    executionCurrentNodeId = getExecutionFocusNodeId(payload);
    executionFailedNodeIds = payload.run.failed_node_ids ?? [];
    executionSkippedNodeIds = payload.run.skipped_node_ids ?? [];
    if (payload.run.status === 'succeeded') {
      executionActiveNodeIds = [];
    } else if (payload.run.status === 'failed') {
      executionActiveNodeIds = [];
    } else if (payload.run.status !== 'running') {
      executionActiveNodeIds = [];
    }

    const modeLabel = payload.mode.startsWith('node')
      ? payload.node?.label ?? executionPresentation.result_labels.node_run
      : executionPresentation.result_labels.workflow_run;
    const summaryParts = [
      `Run #${payload.run.id}`,
      `${payload.run.step_count} step${payload.run.step_count === 1 ? '' : 's'}`,
      `v${payload.run.workflow_version}`,
    ];
    if (payload.message) {
      summaryParts.push(payload.message);
    }

    execution.resultEmpty.hidden = true;
    if (execution.copy) {
      execution.copy.hidden = false;
    }
    execution.result.hidden = false;
    execution.resultTitle.textContent = modeLabel;
    execution.resultSummary.textContent = summaryParts.join(' · ');
    execution.resultBadge.className = `badge ${payload.run.badge_class}`;
    execution.resultBadge.textContent = payload.run.status;
    selectedExecutionTab = resolveDefaultExecutionTab(payload);
    const parsedSteps = parseJsonValue<DesignerRunStep[]>(payload.run.steps_json);
    selectedExecutionStepIndex = Array.isArray(parsedSteps) && parsedSteps.length > 0
      ? parsedSteps.length - 1
      : 0;
    renderExecutionInspector();
    if (payload.run.error) {
      execution.resultError.hidden = false;
      execution.resultError.textContent = payload.run.error;
    } else {
      execution.resultError.hidden = true;
      execution.resultError.textContent = '';
    }
    setExecutionStatus(statusPresentation.label, statusPresentation.badge_class);
    onExecutionStateChange({
      focusNodeId: executionCurrentNodeId,
    });
  }

  async function pollDesignerRunStatus(url: string): Promise<DesignerRunResponse> {
    let lastPayload: DesignerRunResponse | null = null;

    for (let attempt = 0; attempt < 120; attempt += 1) {
      if (attempt > 0) {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
      }

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
      });
      const payload = (await response.json()) as DesignerRunResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          payload && 'detail' in payload && payload.detail
            ? payload.detail
            : executionPresentation.messages.status_fetch_failed,
        );
      }

      lastPayload = payload as DesignerRunResponse;
      renderExecutionResult(lastPayload);
      if (isTerminalRunStatus(lastPayload.run.status)) {
        return lastPayload;
      }
    }

    if (lastPayload) {
      return lastPayload;
    }

    throw new Error(executionPresentation.messages.poll_timeout);
  }

  async function executeDesignerRun(
    url: string,
    options?: {
      nodeId?: string | null;
    },
  ): Promise<void> {
    if (!execution || !url) {
      return;
    }

    const nodeId = options?.nodeId ?? null;
    const selectedNode = getNode(nodeId);
    const isWebhookNodeRun = Boolean(
      selectedNode?.kind === 'trigger' && isWebhookTriggerDefinition(getNodeDefinition(nodeId)),
    );
    const isWebhookWorkflowRun = !nodeId && getWorkflowHasWebhookTriggers();
    const inputData = parseExecutionInput();
    if (inputData === null) {
      return;
    }

    isExecutionPending = true;
    activeExecutionNodeId = getInitialExecutionNodeId(nodeId);
    executionActiveNodeIds = activeExecutionNodeId ? [activeExecutionNodeId] : [];
    executionCompletedNodeIds = [];
    executionCurrentNodeId = activeExecutionNodeId;
    executionFailedNodeIds = [];
    executionSkippedNodeIds = [];
    execution.runButton.disabled = true;
    setExecutionStatus(
      isWebhookNodeRun || isWebhookWorkflowRun
        ? 'Listening for webhook'
        : nodeId
          ? executionPresentation.running_status.node
          : executionPresentation.running_status.workflow,
      isWebhookNodeRun || isWebhookWorkflowRun
        ? executionPresentation.statuses.pending?.badge_class ?? 'text-bg-secondary'
        : executionPresentation.statuses.running?.badge_class ?? 'text-bg-primary',
    );
    onExecutionStateChange({
      focusNodeId: executionCurrentNodeId,
    });

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: buildExecutionRequestBody(inputData),
      });
      const payload = (await response.json()) as DesignerRunResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          payload && 'detail' in payload && payload.detail
            ? payload.detail
            : executionPresentation.messages.execution_failed,
        );
      }
      const runPayload = payload as DesignerRunResponse;
      renderExecutionResult(runPayload);
      if (runPayload.poll_url && !isTerminalRunStatus(runPayload.run.status)) {
        await pollDesignerRunStatus(runPayload.poll_url);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : executionPresentation.messages.execution_failed;
      showExecutionError(message);
      executionActiveNodeIds = [];
      executionCompletedNodeIds = [];
      executionCurrentNodeId = null;
      executionFailedNodeIds = [];
      executionSkippedNodeIds = [];
      setExecutionStatus(
        executionPresentation.statuses.failed?.label ?? 'Failed',
        executionPresentation.statuses.failed?.badge_class ?? 'text-bg-danger',
      );
      onExecutionStateChange({
        focusNodeId: null,
      });
    } finally {
      isExecutionPending = false;
      activeExecutionNodeId = null;
      execution.runButton.disabled = false;
      onExecutionStateChange({
        focusNodeId: executionCurrentNodeId,
      });
    }
  }

  function renderExecutionNodeAction(): void {
    if (!execution) {
      return;
    }

    const selectedNode = getNode(getSelectedNodeId());
    const hasExecutionPayload = Boolean(lastExecutionPayload);
    if (execution.copy) {
      execution.copy.hidden = !hasExecutionPayload;
    }
    if (execution.selectedNode) {
      execution.selectedNode.textContent = selectedNode
        ? selectedNode.label || selectedNode.id
        : executionPresentation.inspector.overview.idle_value;
    }

    if (!selectedNode) {
      execution.nodeRunButtons.forEach((button) => {
        button.hidden = true;
        button.disabled = true;
        button.innerHTML = `
          <i class="mdi mdi-play"></i>
          <span class="ms-1">${executionPresentation.run_button.idle}</span>
        `;
      });
      return;
    }

    const isNodeExecutionPending =
      executionActiveNodeIds.includes(selectedNode.id)
      || (isExecutionPending && activeExecutionNodeId === selectedNode.id);
    execution.nodeRunButtons.forEach((button) => {
      button.hidden = false;
      button.disabled = isExecutionPending || isNodeDisabled(selectedNode);
      button.innerHTML = `
        <i class="mdi ${isNodeExecutionPending ? 'mdi-loading mdi-spin' : 'mdi-play'}"></i>
        <span class="ms-1">${isNodeExecutionPending ? executionPresentation.run_button.running : executionPresentation.run_button.idle}</span>
      `;
    });
  }

  return {
    executeDesignerRun,
    getActiveExecutionNodeId: () => activeExecutionNodeId,
    getExecutionActiveNodeIds: () => executionActiveNodeIds,
    getExecutionCompletedNodeIds: () => executionCompletedNodeIds,
    getExecutionCurrentNodeId: () => executionCurrentNodeId,
    getExecutionFailedNodeIds: () => executionFailedNodeIds,
    getLastExecutionPayload: () => lastExecutionPayload,
    getExecutionSkippedNodeIds: () => executionSkippedNodeIds,
    getIsExecutionPending: () => isExecutionPending,
    renderExecutionNodeAction,
    selectExecutionStep,
    selectExecutionTab,
    syncExecutionSelectionToNode,
  };
}
