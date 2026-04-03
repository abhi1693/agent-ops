import type { ExecutionElements } from '../dom';
import type { WorkflowNode } from '../types';

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

export function createWorkflowDesignerExecutionController(params: {
  buildExecutionRequestBody: (inputData: Record<string, unknown>) => string;
  csrfToken: string;
  execution: ExecutionElements | null;
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
} {
  const {
    buildExecutionRequestBody,
    csrfToken,
    execution,
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

  function renderExecutionResult(payload: DesignerRunResponse): void {
    if (!execution) {
      return;
    }

    const statusLabelByRunStatus: Record<string, { badgeClass: string; label: string }> = {
      failed: {
        badgeClass: 'text-bg-danger',
        label: 'Failed',
      },
      pending: {
        badgeClass: 'text-bg-secondary',
        label: 'Queued',
      },
      running: {
        badgeClass: 'text-bg-primary',
        label: 'Running',
      },
      succeeded: {
        badgeClass: 'text-bg-success',
        label: 'Completed',
      },
    };
    const statusPresentation = statusLabelByRunStatus[payload.run.status] ?? {
      badgeClass: 'text-bg-secondary',
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
      ? payload.node?.label ?? 'Node run'
      : 'Workflow run';
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
    execution.resultOutput.textContent = payload.run.output_json ?? '{}';
    execution.resultTrace.textContent = payload.run.steps_json ?? '[]';
    execution.resultContext.textContent = payload.run.context_json ?? '{}';
    if (payload.run.error) {
      execution.resultError.hidden = false;
      execution.resultError.textContent = payload.run.error;
    } else {
      execution.resultError.hidden = true;
      execution.resultError.textContent = '';
    }
    setExecutionStatus(statusPresentation.label, statusPresentation.badgeClass);
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
        throw new Error(payload && 'detail' in payload && payload.detail ? payload.detail : 'Unable to fetch run status.');
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

    throw new Error('Workflow run polling timed out.');
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
    setExecutionStatus(nodeId ? 'Running node' : 'Running workflow', 'text-bg-primary');
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
        throw new Error(payload && 'detail' in payload && payload.detail ? payload.detail : 'Execution failed.');
      }
      const runPayload = payload as DesignerRunResponse;
      renderExecutionResult(runPayload);
      if (runPayload.poll_url && !isTerminalRunStatus(runPayload.run.status)) {
        await pollDesignerRunStatus(runPayload.poll_url);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Execution failed.';
      showExecutionError(message);
      executionActiveNodeIds = [];
      executionFailedNodeIds = [];
      executionSucceededNodeId = null;
      setExecutionStatus('Failed', 'text-bg-danger');
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
        <span class="ms-1">Run node</span>
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
      <span class="ms-1">${isNodeExecutionPending ? 'Running node' : 'Run node'}</span>
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
  };
}
