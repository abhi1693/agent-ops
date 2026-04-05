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

type ConfigPathSegment = string | number;

function parseConfigPath(path: string): ConfigPathSegment[] {
  return path
    .split('.')
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0)
    .map((segment) => (/^\d+$/.test(segment) ? Number.parseInt(segment, 10) : segment));
}

export function getConfigValueAtPath(
  config: Record<string, unknown> | undefined,
  path: string,
): unknown {
  let current: unknown = config;
  for (const segment of parseConfigPath(path)) {
    if (typeof segment === 'number') {
      if (!Array.isArray(current) || segment >= current.length) {
        return undefined;
      }
      current = current[segment];
      continue;
    }
    if (!current || typeof current !== 'object' || Array.isArray(current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

function pruneEmptyConfigContainers(value: unknown): unknown {
  if (Array.isArray(value)) {
    const nextValue = value
      .map((item) => pruneEmptyConfigContainers(item))
      .filter((item) => item !== undefined);
    return nextValue.length > 0 ? nextValue : undefined;
  }

  if (value && typeof value === 'object') {
    const nextValue = Object.entries(value as Record<string, unknown>).reduce<Record<string, unknown>>(
      (accumulator, [key, item]) => {
        const nextItem = pruneEmptyConfigContainers(item);
        if (nextItem !== undefined) {
          accumulator[key] = nextItem;
        }
        return accumulator;
      },
      {},
    );
    return Object.keys(nextValue).length > 0 ? nextValue : undefined;
  }

  return value;
}

export function setConfigValueAtPath(
  config: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  const segments = parseConfigPath(path);
  if (segments.length === 0) {
    return config;
  }

  const root: Record<string, unknown> = { ...config };
  let current: unknown = root;

  for (let index = 0; index < segments.length - 1; index += 1) {
    const segment = segments[index];
    const nextSegment = segments[index + 1];

    if (typeof segment === 'number') {
      if (!Array.isArray(current)) {
        return config;
      }

      const nextCurrent = current[segment];
      const nextContainer =
        nextCurrent && typeof nextCurrent === 'object'
          ? Array.isArray(nextCurrent)
            ? [...nextCurrent]
            : { ...(nextCurrent as Record<string, unknown>) }
          : typeof nextSegment === 'number'
            ? []
            : {};
      current[segment] = nextContainer;
      current = nextContainer;
      continue;
    }

    if (!current || typeof current !== 'object' || Array.isArray(current)) {
      return config;
    }

    const currentRecord = current as Record<string, unknown>;
    const nextCurrent = currentRecord[segment];
    const nextContainer =
      nextCurrent && typeof nextCurrent === 'object'
        ? Array.isArray(nextCurrent)
          ? [...nextCurrent]
          : { ...(nextCurrent as Record<string, unknown>) }
        : typeof nextSegment === 'number'
          ? []
          : {};
    currentRecord[segment] = nextContainer;
    current = nextContainer;
  }

  const lastSegment = segments[segments.length - 1];
  const normalizedValue = pruneEmptyConfigContainers(value);

  if (typeof lastSegment === 'number') {
    if (!Array.isArray(current)) {
      return config;
    }
    if (normalizedValue === undefined) {
      current.splice(lastSegment, 1);
    } else {
      current[lastSegment] = normalizedValue;
    }
  } else if (current && typeof current === 'object' && !Array.isArray(current)) {
    const currentRecord = current as Record<string, unknown>;
    if (normalizedValue === undefined) {
      delete currentRecord[lastSegment];
    } else {
      currentRecord[lastSegment] = normalizedValue;
    }
  }

  return (pruneEmptyConfigContainers(root) as Record<string, unknown>) ?? {};
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
  return Boolean(node?.disabled);
}

export function supportsNodeDisabledState(node: WorkflowNode | undefined): boolean {
  return node?.kind === 'agent' || node?.kind === 'tool';
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

export function getTemplateFieldValueAtPath(
  node: WorkflowNode,
  path: string,
  prettyJson = false,
): string {
  return stringifyConfigValue(getConfigValueAtPath(node.config, path), prettyJson);
}

export function normalizeFieldInputValue(
  field: Pick<WorkflowNodeTemplateField, 'type' | 'value_type'>,
  value: string,
): unknown {
  if (value === '') {
    return undefined;
  }

  if (field.type === 'textarea' && field.value_type === 'json') {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }

  if (field.value_type === 'integer') {
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? value : parsed;
  }

  if (field.value_type === 'number') {
    const parsed = Number.parseFloat(value);
    return Number.isNaN(parsed) ? value : parsed;
  }

  if (field.value_type === 'boolean') {
    if (value === 'true') {
      return true;
    }
    if (value === 'false') {
      return false;
    }
  }

  return value;
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
