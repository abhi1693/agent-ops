import type { ExecutionElements } from '../dom';
import type { WorkflowExecutionPresentation, WorkflowNode } from '../types';
import { escapeHtml, formatKindLabel } from '../utils';

type DesignerRunResponse = {
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
    status: string;
    step_count: number;
    steps_json: string | null;
    trigger_mode: string;
    workflow_version: number;
  };
};

export type ExecutionInspectorTab = 'overview' | 'output' | 'input' | 'context' | 'steps' | 'trace';

type DesignerRunStep = {
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
  getInitialExecutionNodeId: (nodeId: string | null) => string | null;
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getSelectedNodeId: () => string | null;
  getSettingsNodeId: () => string | null;
  isTerminalRunStatus: (status: string) => boolean;
  onExecutionStateChange: () => void;
  openNodeSettings: (nodeId: string) => void;
}): {
  executeDesignerRun: (
    url: string,
    options?: {
      nodeId?: string | null;
    },
  ) => Promise<void>;
  getActiveExecutionNodeId: () => string | null;
  getExecutionActiveNodeIds: () => string[];
  getExecutionFailedNodeIds: () => string[];
  getExecutionSucceededNodeId: () => string | null;
  getIsExecutionPending: () => boolean;
  renderExecutionNodeAction: () => void;
  selectExecutionStep: (stepIndex: number) => void;
  selectExecutionTab: (tab: ExecutionInspectorTab) => void;
} {
  const {
    buildExecutionRequestBody,
    csrfToken,
    execution,
    executionPresentation,
    getInitialExecutionNodeId,
    getNode,
    getSelectedNodeId,
    getSettingsNodeId,
    isTerminalRunStatus,
    onExecutionStateChange,
    openNodeSettings,
  } = params;

  let isExecutionPending = false;
  let activeExecutionNodeId: string | null = null;
  let executionActiveNodeIds: string[] = [];
  let executionFailedNodeIds: string[] = [];
  let executionSucceededNodeId: string | null = null;
  let selectedExecutionTab: ExecutionInspectorTab = 'overview';
  let selectedExecutionStepIndex = 0;
  let lastExecutionPayload: DesignerRunResponse | null = null;

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

  function resolveDefaultExecutionTab(payload: DesignerRunResponse): ExecutionInspectorTab {
    const parsedSteps = parseJsonValue<DesignerRunStep[]>(payload.run.steps_json);
    if (Array.isArray(parsedSteps) && parsedSteps.length > 0) {
      return 'steps';
    }

    if (parseJsonValue(payload.run.output_json) !== null) {
      return 'output';
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
    const overviewLabels = executionPresentation.inspector.overview;
    const selectedStep = steps[selectedExecutionStepIndex] ?? null;

    const stepListMarkup = steps.length > 0
      ? `
          <div class="workflow-editor-execution-step-list">
            ${steps
              .map((step, index) => {
                const isSelected = index === selectedExecutionStepIndex;
                const title = step.label || step.node_id || `Step ${index + 1}`;
                const meta = [step.kind ? formatKindLabel(step.kind) : '', step.type || '']
                  .filter((part) => part)
                  .join(' · ');

                return `
                  <button
                    type="button"
                    class="workflow-editor-execution-step-item${isSelected ? ' is-active' : ''}"
                    data-workflow-execution-step-index="${index}"
                  >
                    <span class="workflow-editor-execution-step-index">${index + 1}</span>
                    <span class="workflow-editor-execution-step-copy">
                      <span class="workflow-editor-execution-step-title">${escapeHtml(title)}</span>
                      <span class="workflow-editor-execution-step-meta">${escapeHtml(meta)}</span>
                    </span>
                  </button>
                `;
              })
              .join('')}
          </div>
        `
      : `<div class="workflow-editor-settings-empty">${escapeHtml(executionPresentation.inspector.steps.empty)}</div>`;

    const stepDetailMarkup = selectedStep
      ? `
          <div class="workflow-editor-execution-step-detail-head">
            <div class="workflow-editor-execution-step-detail-title">
              ${escapeHtml(selectedStep.label || selectedStep.node_id || executionPresentation.inspector.steps.title)}
            </div>
            <div class="workflow-editor-execution-step-detail-meta">
              ${escapeHtml(
                [selectedStep.kind ? formatKindLabel(selectedStep.kind) : '', selectedStep.type || '']
                  .filter((part) => part)
                  .join(' · '),
              )}
            </div>
          </div>
          <div class="workflow-editor-execution-group">
            <div class="text-secondary mb-1">${escapeHtml(executionPresentation.inspector.steps.result_label)}</div>
            <pre class="workflow-json-preview mb-0">${escapeHtml(formatJsonValue(selectedStep.result ?? {}, '{}'))}</pre>
          </div>
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
        <div class="workflow-editor-execution-steps-layout">
          ${stepListMarkup}
          <div class="workflow-editor-execution-step-detail">
            ${stepDetailMarkup}
          </div>
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
        ${(Object.keys(tabs) as ExecutionInspectorTab[])
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

  function renderExecutionResult(payload: DesignerRunResponse): void {
    if (!execution) {
      return;
    }

    lastExecutionPayload = payload;
    const statusPresentation = executionPresentation.statuses[payload.run.status] ?? {
      badge_class: executionPresentation.default_status.badge_class,
      label: payload.run.status,
    };
    executionActiveNodeIds = payload.run.active_node_ids ?? [];
    executionFailedNodeIds = payload.run.failed_node_ids ?? [];
    executionSucceededNodeId = null;
    if (payload.run.status === 'succeeded') {
      executionSucceededNodeId = payload.run.last_completed_node_id;
      executionFailedNodeIds = [];
      executionActiveNodeIds = [];
    } else if (payload.run.status === 'failed') {
      executionActiveNodeIds = [];
    } else if (payload.run.status !== 'running') {
      executionActiveNodeIds = [];
      executionFailedNodeIds = [];
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
    onExecutionStateChange();
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
    if (nodeId && getSettingsNodeId() !== nodeId) {
      openNodeSettings(nodeId);
    } else if (!nodeId && !getSettingsNodeId() && getSelectedNodeId()) {
      openNodeSettings(getSelectedNodeId() as string);
    }

    const inputData = parseExecutionInput();
    if (inputData === null) {
      return;
    }

    isExecutionPending = true;
    activeExecutionNodeId = getInitialExecutionNodeId(nodeId);
    executionActiveNodeIds = activeExecutionNodeId ? [activeExecutionNodeId] : [];
    executionFailedNodeIds = [];
    executionSucceededNodeId = null;
    execution.runButton.disabled = true;
    setExecutionStatus(
      nodeId ? executionPresentation.running_status.node : executionPresentation.running_status.workflow,
      executionPresentation.statuses.running?.badge_class ?? 'text-bg-primary',
    );
    onExecutionStateChange();

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
      executionFailedNodeIds = [];
      executionSucceededNodeId = null;
      setExecutionStatus(
        executionPresentation.statuses.failed?.label ?? 'Failed',
        executionPresentation.statuses.failed?.badge_class ?? 'text-bg-danger',
      );
      onExecutionStateChange();
    } finally {
      isExecutionPending = false;
      activeExecutionNodeId = null;
      execution.runButton.disabled = false;
      onExecutionStateChange();
    }
  }

  function renderExecutionNodeAction(): void {
    if (!execution?.nodeRunButton) {
      return;
    }

    const settingsNode = getNode(getSettingsNodeId());
    if (!settingsNode) {
      execution.nodeRunButton.hidden = true;
      execution.nodeRunButton.disabled = true;
      execution.nodeRunButton.innerHTML = `
        <i class="mdi mdi-play"></i>
        <span class="ms-1">${executionPresentation.run_button.idle}</span>
      `;
      return;
    }

    const isNodeExecutionPending =
      executionActiveNodeIds.includes(settingsNode.id)
      || (isExecutionPending && activeExecutionNodeId === settingsNode.id);
    execution.nodeRunButton.hidden = false;
    execution.nodeRunButton.disabled = isExecutionPending;
    execution.nodeRunButton.innerHTML = `
      <i class="mdi ${isNodeExecutionPending ? 'mdi-loading mdi-spin' : 'mdi-play'}"></i>
      <span class="ms-1">${isNodeExecutionPending ? executionPresentation.run_button.running : executionPresentation.run_button.idle}</span>
    `;
  }

  return {
    executeDesignerRun,
    getActiveExecutionNodeId: () => activeExecutionNodeId,
    getExecutionActiveNodeIds: () => executionActiveNodeIds,
    getExecutionFailedNodeIds: () => executionFailedNodeIds,
    getExecutionSucceededNodeId: () => executionSucceededNodeId,
    getIsExecutionPending: () => isExecutionPending,
    renderExecutionNodeAction,
    selectExecutionStep,
    selectExecutionTab,
  };
}
