import type {
  WorkflowNode,
  WorkflowNodeTemplateField,
  WorkflowToolDefinition,
  WorkflowTriggerDefinition,
} from './types';

export function parseJsonScript<T>(scriptId: string, fallback: T): T {
  const script = document.getElementById(scriptId);
  if (!script || !script.textContent) {
    return fallback;
  }

  try {
    return JSON.parse(script.textContent) as T;
  } catch (error) {
    console.error(error);
    return fallback;
  }
}

export function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function createId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function getNodeTitle(node: WorkflowNode): string {
  return node.label || node.kind || node.type;
}

export function formatKindLabel(kind: string): string {
  return kind
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function stringifyConfigValue(value: unknown, pretty = false): string {
  if (value === undefined || value === null) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, pretty ? 2 : 0);
    } catch (error) {
      console.error(error);
    }
  }

  return String(value);
}

export function getConfigString(
  config: Record<string, unknown> | undefined,
  key: string,
  prettyJson = false,
): string {
  const value = config?.[key];
  return stringifyConfigValue(value, prettyJson);
}

export function getTriggerType(config: Record<string, unknown> | undefined): string {
  const triggerType = getConfigString(config, 'type');
  if (triggerType) {
    return triggerType;
  }
  return 'manual';
}

export function getToolName(config: Record<string, unknown> | undefined): string {
  const toolName = getConfigString(config, 'tool_name');
  if (toolName) {
    return toolName;
  }

  const legacyOperation = getConfigString(config, 'operation');
  if (legacyOperation) {
    return legacyOperation;
  }

  return 'passthrough';
}

export function formatCount(value: number, singular: string, plural = `${singular}s`): string {
  return `${value} ${value === 1 ? singular : plural}`;
}

export function isNodeDisabled(node: WorkflowNode | undefined): boolean {
  return Boolean(node?.config && node.config['disabled']);
}

export function getNodeStatusLabel(node: WorkflowNode | undefined, isRunning = false): string {
  if (!node) {
    return 'Idle';
  }
  if (isRunning) {
    return 'Running';
  }
  if (isNodeDisabled(node)) {
    return 'Disabled';
  }
  return 'Ready';
}

export function getNodeSubtitle(
  node: WorkflowNode,
  triggerDefinitionMap: Map<string, WorkflowTriggerDefinition>,
  toolDefinitionMap: Map<string, WorkflowToolDefinition>,
): string {
  if (node.kind === 'trigger') {
    return triggerDefinitionMap.get(getTriggerType(node.config))?.label ?? 'Workflow entry point';
  }

  if (node.kind === 'tool') {
    return toolDefinitionMap.get(getToolName(node.config))?.label ?? 'Runs a workflow tool';
  }

  if (node.kind === 'condition') {
    const path = getConfigString(node.config, 'path');
    const operator = getConfigString(node.config, 'operator');
    if (path && operator) {
      return `${path} • ${formatKindLabel(operator)}`;
    }
    if (path) {
      return path;
    }
    return 'Branches workflow execution';
  }

  if (node.kind === 'response') {
    const status = getConfigString(node.config, 'status');
    return status ? `Marks run as ${status.replace(/_/g, ' ')}` : 'Completes the workflow';
  }

  if (node.kind === 'agent') {
    const outputKey = getConfigString(node.config, 'output_key');
    return outputKey ? `Writes to ${outputKey}` : 'Writes a message into workflow context';
  }

  return 'Custom workflow node';
}

export function getTemplateFieldValue(
  node: WorkflowNode,
  field: WorkflowNodeTemplateField,
): string {
  if (node.kind === 'trigger' && field.key === 'type') {
    return getTriggerType(node.config);
  }
  if (node.kind === 'tool' && field.key === 'tool_name') {
    return getToolName(node.config);
  }

  return getConfigString(node.config, field.key, field.type === 'textarea');
}
