import type {
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeTemplateField,
} from '../types';
import {
  escapeHtml,
  getConfigString,
  getTemplateFieldBinding,
} from '../utils';

function pushUniqueSuggestion(target: string[], seen: Set<string>, value: string | null | undefined): void {
  const normalizedValue = (value ?? '').trim();
  if (!normalizedValue || seen.has(normalizedValue)) {
    return;
  }
  seen.add(normalizedValue);
  target.push(normalizedValue);
}

function collectContextPaths(
  value: unknown,
  prefix: string,
  target: string[],
  seen: Set<string>,
  depth = 0,
): void {
  pushUniqueSuggestion(target, seen, prefix);
  if (depth >= 3) {
    return;
  }

  if (Array.isArray(value)) {
    value.slice(0, 3).forEach((entry, index) => {
      collectContextPaths(entry, `${prefix}.${index}`, target, seen, depth + 1);
    });
    return;
  }

  if (!value || typeof value !== 'object') {
    return;
  }

  Object.entries(value as Record<string, unknown>)
    .slice(0, 10)
    .forEach(([key, entry]) => {
      if (!key.trim()) {
        return;
      }
      collectContextPaths(entry, `${prefix}.${key}`, target, seen, depth + 1);
    });
}

function getUpstreamResultPaths(params: {
  getNode: (nodeId: string | null) => WorkflowNode | undefined;
  nodeId: string;
  workflowDefinition: WorkflowDefinition;
}): string[] {
  const suggestions: string[] = [];
  const seenSuggestions = new Set<string>();
  const queue = [params.nodeId];
  const visitedNodeIds = new Set<string>([params.nodeId]);

  while (queue.length > 0) {
    const currentNodeId = queue.shift();
    if (!currentNodeId) {
      continue;
    }

    params.workflowDefinition.edges
      .filter((edge) => edge.target === currentNodeId)
      .forEach((edge) => {
        const sourceNode = params.getNode(edge.source);
        if (!sourceNode) {
          return;
        }

        pushUniqueSuggestion(
          suggestions,
          seenSuggestions,
          getConfigString(sourceNode.config, 'output_key').trim(),
        );

        if (!visitedNodeIds.has(sourceNode.id)) {
          visitedNodeIds.add(sourceNode.id);
          queue.push(sourceNode.id);
        }
      });
  }

  return suggestions;
}

export function getAvailableInputPaths(params: {
  executionInputData: Record<string, unknown>;
  getNode: (nodeId: string | null) => WorkflowNode | undefined;
  nodeId: string;
  workflowDefinition: WorkflowDefinition;
}): string[] {
  const suggestions: string[] = [];
  const seenSuggestions = new Set<string>();

  collectContextPaths(params.executionInputData, 'trigger.payload', suggestions, seenSuggestions);
  pushUniqueSuggestion(suggestions, seenSuggestions, 'workflow.scope_label');
  pushUniqueSuggestion(suggestions, seenSuggestions, 'workflow.name');
  getUpstreamResultPaths({
    getNode: params.getNode,
    nodeId: params.nodeId,
    workflowDefinition: params.workflowDefinition,
  }).forEach((path) => {
    pushUniqueSuggestion(suggestions, seenSuggestions, path);
  });

  return suggestions.slice(0, 12);
}

export function renderSettingAssistMarkup(params: {
  binding?: 'literal' | 'path' | 'template';
  field: WorkflowNodeTemplateField;
  label: string;
  suggestions: string[];
}): string {
  if (params.suggestions.length === 0) {
    return '';
  }

  const binding = params.binding ?? getTemplateFieldBinding(params.field);
  const chips = params.suggestions
    .map(
      (suggestion) => `
        <button
          type="button"
          class="workflow-editor-settings-chip"
          data-node-setting-chip-key="${escapeHtml(params.field.key)}"
          data-node-setting-chip-value="${escapeHtml(suggestion)}"
          data-node-setting-chip-binding="${escapeHtml(binding)}"
          title="${escapeHtml(suggestion)}"
        >
          ${escapeHtml(suggestion)}
        </button>
      `,
    )
    .join('');

  return `
    <div class="workflow-editor-settings-assist">
      <div class="workflow-editor-settings-assist-label">${escapeHtml(params.label)}</div>
      <div class="workflow-editor-settings-chip-list">
        ${chips}
      </div>
    </div>
  `;
}

export function buildTemplateInsertionValue(
  control: HTMLInputElement | HTMLTextAreaElement,
  path: string,
): string {
  const token = `{{ ${path} }}`;
  const useCurrentSelection = document.activeElement === control;
  const selectionStart = useCurrentSelection && typeof control.selectionStart === 'number'
    ? control.selectionStart
    : control.value.length;
  const selectionEnd = useCurrentSelection && typeof control.selectionEnd === 'number'
    ? control.selectionEnd
    : selectionStart;

  return `${control.value.slice(0, selectionStart)}${token}${control.value.slice(selectionEnd)}`;
}

export function getNodeSettingControl(
  settingsFields: HTMLElement,
  key: string,
): HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null {
  return (
    Array.from(
      settingsFields.querySelectorAll<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
        '[data-node-setting-key]',
      ),
    ).find((element) => element.dataset.nodeSettingKey === key) ?? null
  );
}
