import type {
  WorkflowNodeTemplateField,
  WorkflowSettingsPresentation,
} from '../../types';
import { escapeHtml } from '../../utils';

export function renderRequiredBadge(params: {
  badgeText: string;
  fieldId: string;
  isRequired?: boolean;
  label: string;
}): string {
  const { badgeText, fieldId, isRequired = false, label } = params;
  if (!isRequired) {
    return `<label class="form-label" for="${escapeHtml(fieldId)}">${escapeHtml(label)}</label>`;
  }

  return `
    <div class="workflow-editor-settings-label-row">
      <label class="form-label" for="${escapeHtml(fieldId)}">${escapeHtml(label)}</label>
      <span class="workflow-editor-settings-required-badge">${escapeHtml(badgeText)}</span>
    </div>
  `;
}

export function renderFieldLabelMarkup(params: {
  field: WorkflowNodeTemplateField;
  fieldId: string;
  fieldInputMode: 'expression' | 'static';
  presentation: WorkflowSettingsPresentation;
  supportsInputMode: boolean;
}): string {
  const requiredBadge = params.field.required
    ? `<span class="workflow-editor-settings-required-badge">${escapeHtml(params.presentation.controls.required_badge)}</span>`
    : '';

  if (!params.supportsInputMode) {
    return `
      <div class="workflow-editor-settings-label-row">
        <label class="form-label" for="${escapeHtml(params.fieldId)}">${escapeHtml(params.field.label)}</label>
        ${requiredBadge}
      </div>
    `;
  }

  return `
    <div class="workflow-editor-settings-label-row">
      <label class="form-label" for="${escapeHtml(params.fieldId)}">${escapeHtml(params.field.label)}</label>
      <div class="workflow-editor-settings-label-actions">
        ${requiredBadge}
        <div class="workflow-editor-settings-mode-toggle" role="group" aria-label="${escapeHtml(`${params.field.label} ${params.presentation.controls.mode_suffix}`)}">
          <button
            type="button"
            class="workflow-editor-settings-mode-button${params.fieldInputMode === 'static' ? ' is-active' : ''}"
            data-node-setting-mode-key="${escapeHtml(params.field.key)}"
            data-node-setting-mode="static"
          >
            ${escapeHtml(params.presentation.controls.mode_static)}
          </button>
          <button
            type="button"
            class="workflow-editor-settings-mode-button${params.fieldInputMode === 'expression' ? ' is-active' : ''}"
            data-node-setting-mode-key="${escapeHtml(params.field.key)}"
            data-node-setting-mode="expression"
          >
            ${escapeHtml(params.presentation.controls.mode_expression)}
          </button>
        </div>
      </div>
    </div>
  `;
}

export function renderFieldHelpText(helpText?: string): string {
  return helpText?.trim()
    ? `<div class="workflow-editor-settings-help">${escapeHtml(helpText)}</div>`
    : '';
}
