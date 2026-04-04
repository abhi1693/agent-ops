import type {
  WorkflowNode,
  WorkflowNodeTemplateOption,
  WorkflowNodeTemplateField,
} from './types';

export type WorkflowNodeFieldBinding = 'literal' | 'path' | 'template';
export type WorkflowNodeFieldInputMode = 'expression' | 'static';
export type WorkflowNodeFieldUiGroup = 'advanced' | 'input' | 'result';
export const WORKFLOW_NODE_INPUT_MODES_KEY = '__input_modes';

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

export function formatCount(value: number, singular: string, plural = `${singular}s`): string {
  return `${value} ${value === 1 ? singular : plural}`;
}

export function isNodeDisabled(node: WorkflowNode | undefined): boolean {
  return Boolean(node?.config && node.config['disabled']);
}

export function isTemplateFieldVisible(
  node: WorkflowNode,
  field: WorkflowNodeTemplateField,
): boolean {
  if (!field.visible_when) {
    return true;
  }

  return Object.entries(field.visible_when).every(([configKey, allowedValues]) => {
    const currentValue = getConfigString(node.config, configKey);
    return allowedValues.includes(currentValue);
  });
}

export function getTemplateFieldOptions(
  node: WorkflowNode,
  field: WorkflowNodeTemplateField,
): WorkflowNodeTemplateOption[] {
  if (!field.options_by_field) {
    return field.options ?? [];
  }

  for (const [configKey, optionMap] of Object.entries(field.options_by_field)) {
    const configValue = getConfigString(node.config, configKey);
    const fieldOptions = optionMap[configValue];
    if (fieldOptions) {
      return fieldOptions;
    }
  }

  return field.options ?? [];
}

export function getTemplateFieldValue(
  node: WorkflowNode,
  field: WorkflowNodeTemplateField,
): string {
  return getConfigString(node.config, field.key, field.type === 'textarea');
}

function getNodeFieldInputModes(
  node: WorkflowNode,
): Record<string, WorkflowNodeFieldInputMode> {
  const rawModes = node.config?.[WORKFLOW_NODE_INPUT_MODES_KEY];
  if (!rawModes || typeof rawModes !== 'object' || Array.isArray(rawModes)) {
    return {};
  }

  const normalizedModes: Record<string, WorkflowNodeFieldInputMode> = {};
  Object.entries(rawModes as Record<string, unknown>).forEach(([key, value]) => {
    if (value === 'expression' || value === 'static') {
      normalizedModes[key] = value;
    }
  });
  return normalizedModes;
}

export function getTemplateFieldBinding(
  field: WorkflowNodeTemplateField,
): WorkflowNodeFieldBinding {
  if (field.binding) {
    return field.binding;
  }

  const normalizedKey = field.key.trim().toLowerCase();
  const normalizedLabel = field.label.trim().toLowerCase();

  if (
    normalizedKey === 'output_key' ||
    normalizedKey === 'value_path' ||
    normalizedKey === 'path' ||
    normalizedLabel.includes('context path') ||
    normalizedLabel.includes('value path') ||
    normalizedLabel.includes('save result as')
  ) {
    return 'path';
  }

  if (
    normalizedKey === 'template' ||
    normalizedKey === 'query' ||
    normalizedKey === 'query_json' ||
    normalizedKey === 'arguments_json' ||
    normalizedKey === 'command' ||
    normalizedKey.endsWith('_prompt')
  ) {
    return 'template';
  }

  return 'literal';
}

export function supportsTemplateFieldInputMode(
  field: WorkflowNodeTemplateField,
): boolean {
  return (
    (field.type === 'text' || field.type === 'textarea') &&
    getTemplateFieldUiGroup(field) !== 'result'
  );
}

export function getDefaultTemplateFieldInputMode(
  field: WorkflowNodeTemplateField,
): WorkflowNodeFieldInputMode {
  void field;
  return 'static';
}

export function getRuntimeTemplateFieldInputModeDefault(
  field: WorkflowNodeTemplateField,
): WorkflowNodeFieldInputMode {
  return getTemplateFieldBinding(field) === 'template' ? 'expression' : 'static';
}

export function inferTemplateFieldInputMode(
  node: WorkflowNode,
  field: WorkflowNodeTemplateField,
): WorkflowNodeFieldInputMode {
  void node;
  return getDefaultTemplateFieldInputMode(field);
}

export function getTemplateFieldInputMode(
  node: WorkflowNode,
  field: WorkflowNodeTemplateField,
): WorkflowNodeFieldInputMode {
  if (!supportsTemplateFieldInputMode(field)) {
    return 'static';
  }

  return (
    getNodeFieldInputModes(node)[field.key] ??
    inferTemplateFieldInputMode(node, field)
  );
}

export function getTemplateFieldUiGroup(
  field: WorkflowNodeTemplateField,
): WorkflowNodeFieldUiGroup {
  if (field.ui_group) {
    return field.ui_group;
  }

  const normalizedKey = field.key.trim().toLowerCase();
  const normalizedLabel = field.label.trim().toLowerCase();
  const binding = getTemplateFieldBinding(field);

  if (
    normalizedKey === 'output_key' ||
    normalizedLabel.includes('save result as')
  ) {
    return 'result';
  }

  if (
    binding === 'template' ||
    normalizedKey === 'value_path' ||
    normalizedKey === 'path' ||
    normalizedKey === 'remote_tool_name'
  ) {
    return 'input';
  }

  return 'advanced';
}
