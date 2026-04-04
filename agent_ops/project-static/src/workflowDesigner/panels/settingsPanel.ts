import { renderSettingAssistMarkup } from './settingsAssist';
import type {
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowSettingsPresentation,
  WorkflowNodeTemplateField,
  WorkflowNodeTemplateOption,
} from '../types';
import { escapeHtml } from '../utils';
import {
  getTemplateFieldBinding,
  getTemplateFieldInputMode,
  getTemplateFieldUiGroup,
  getTemplateFieldValue,
  isTemplateFieldVisible,
  supportsTemplateFieldInputMode,
} from '../utils';

export function renderSettingsSection(params: {
  body: string;
  description: string;
  title: string;
}): string {
  if (!params.body.trim()) {
    return '';
  }

  return `
    <section class="workflow-editor-settings-section">
      <div class="workflow-editor-settings-section-head">
        <div class="workflow-editor-settings-section-title">${escapeHtml(params.title)}</div>
        <div class="workflow-editor-settings-section-description">${escapeHtml(params.description)}</div>
      </div>
      <div class="workflow-editor-settings-section-body">
        ${params.body}
      </div>
    </section>
  `;
}

export function renderSettingsOverviewSection(params: {
  presentation: WorkflowSettingsPresentation;
  nodeDefinitionLabel: string;
  nodeId: string;
}): string {
  const overviewPresentation = params.presentation.groups.overview;
  const overviewFields = overviewPresentation.fields ?? {};

  return `
    <section class="workflow-editor-settings-section">
      <div class="workflow-editor-settings-section-head">
        <div class="workflow-editor-settings-section-title">${escapeHtml(overviewPresentation.title)}</div>
        <div class="workflow-editor-settings-section-description">${escapeHtml(overviewPresentation.description)}</div>
      </div>
      <div class="workflow-editor-settings-section-body">
        <div class="workflow-editor-settings-group">
          <div class="workflow-editor-settings-help">${escapeHtml(overviewFields.type ?? 'Type')}</div>
          <div class="workflow-editor-settings-preview">${escapeHtml(params.nodeDefinitionLabel)}</div>
        </div>
        <div class="workflow-editor-settings-group">
          <div class="workflow-editor-settings-help">${escapeHtml(overviewFields.node_id ?? 'Node id')}</div>
          <div class="workflow-editor-settings-expression-hint"><code>${escapeHtml(params.nodeId)}</code></div>
        </div>
      </div>
    </section>
  `;
}

export function renderSettingsIdentitySection(params: {
  nodeId: string;
  nodeLabel: string;
  presentation: WorkflowSettingsPresentation;
}): string {
  const identityPresentation = params.presentation.groups.identity;
  const identityFields = identityPresentation.fields ?? {};

  return `
    <section class="workflow-editor-settings-section">
      <div class="workflow-editor-settings-section-head">
        <div class="workflow-editor-settings-section-title">${escapeHtml(identityPresentation.title)}</div>
        <div class="workflow-editor-settings-section-description">${escapeHtml(identityPresentation.description)}</div>
      </div>
      <div class="workflow-editor-settings-section-body">
        <div class="workflow-editor-settings-group">
          <label class="form-label" for="workflow-node-label-${escapeHtml(params.nodeId)}">${escapeHtml(identityFields.node_name ?? 'Node name')}</label>
          <input
            id="workflow-node-label-${escapeHtml(params.nodeId)}"
            type="text"
            class="form-control workflow-editor-settings-control"
            value="${escapeHtml(params.nodeLabel)}"
            data-node-setting-label
          >
        </div>
      </div>
    </section>
  `;
}

export function renderNodeSettingsFieldsMarkup(params: {
  availableInputPaths: string[];
  getFieldOptions: (field: WorkflowNodeTemplateField) => WorkflowNodeTemplateOption[];
  getNodeTargetOptions: () => Array<{ label: string; value: string }>;
  node: WorkflowNode;
  nodeDefinition: WorkflowNodeDefinition;
  presentation: WorkflowSettingsPresentation;
}): string {
  const visibleFields = params.nodeDefinition.fields.filter((field) => isTemplateFieldVisible(params.node, field));

  function renderSettingsField(field: WorkflowNodeTemplateField): string {
    const fieldId = `workflow-node-setting-${params.node.id}-${field.key}`;
    const value = getTemplateFieldValue(params.node, field);
    const fieldBinding = getTemplateFieldBinding(field);
    const fieldGroup = getTemplateFieldUiGroup(field);
    const supportsInputMode = supportsTemplateFieldInputMode(field);
    const fieldInputMode = getTemplateFieldInputMode(params.node, field);
    const labelMarkup = supportsInputMode
      ? `
          <div class="workflow-editor-settings-label-row">
            <label class="form-label" for="${escapeHtml(fieldId)}">${escapeHtml(field.label)}</label>
            <div class="workflow-editor-settings-mode-toggle" role="group" aria-label="${escapeHtml(`${field.label} ${params.presentation.controls.mode_suffix}`)}">
              <button
                type="button"
                class="workflow-editor-settings-mode-button${fieldInputMode === 'static' ? ' is-active' : ''}"
                data-node-setting-mode-key="${escapeHtml(field.key)}"
                data-node-setting-mode="static"
              >
                ${escapeHtml(params.presentation.controls.mode_static)}
              </button>
              <button
                type="button"
                class="workflow-editor-settings-mode-button${fieldInputMode === 'expression' ? ' is-active' : ''}"
                data-node-setting-mode-key="${escapeHtml(field.key)}"
                data-node-setting-mode="expression"
              >
                ${escapeHtml(params.presentation.controls.mode_expression)}
              </button>
            </div>
          </div>
        `
      : `<label class="form-label" for="${escapeHtml(fieldId)}">${escapeHtml(field.label)}</label>`;
    const helpText = field.help_text
      ? `<div class="workflow-editor-settings-help">${escapeHtml(field.help_text)}</div>`
      : '';
    const expressionHint = supportsInputMode && fieldInputMode === 'expression'
      ? `
          <div class="workflow-editor-settings-expression-hint">
            ${escapeHtml(params.presentation.controls.expression_hint)}
          </div>
        `
      : '';
    const fieldPreview = fieldBinding === 'path' && value
      ? `
          <div class="workflow-editor-settings-preview">
            ${escapeHtml(
              fieldGroup === 'result'
                ? `Writes to context.${value}`
                : `Reads from context.${value}`,
            )}
          </div>
        `
      : '';
    const assistMarkup = (() => {
      if (supportsInputMode && fieldInputMode === 'expression') {
        return renderSettingAssistMarkup({
          binding: 'template',
          field,
          label: 'Insert result or trigger value',
          suggestions: params.availableInputPaths,
        });
      }

      if (fieldBinding === 'path' && fieldGroup === 'input') {
        return renderSettingAssistMarkup({
          field,
          label: 'Use context path',
          suggestions: params.availableInputPaths,
        });
      }

      return '';
    })();

    if (field.type === 'textarea') {
      return `
        <div class="workflow-editor-settings-group">
          ${labelMarkup}
          <textarea
            id="${escapeHtml(fieldId)}"
            class="form-control workflow-editor-settings-control"
            rows="${field.rows ?? 4}"
            data-node-setting-key="${escapeHtml(field.key)}"
            data-node-setting-type="${escapeHtml(field.type)}"
          >${escapeHtml(value)}</textarea>
          ${helpText}
          ${expressionHint}
          ${fieldPreview}
          ${assistMarkup}
        </div>
      `;
    }

    if (field.type === 'select' || field.type === 'node_target') {
      const options = (field.type === 'node_target'
        ? params.getNodeTargetOptions()
        : params.getFieldOptions(field)
      )
        .map(
          (option) => `
            <option value="${escapeHtml(option.value)}"${option.value === value ? ' selected' : ''}>
              ${escapeHtml(option.label)}
            </option>
          `,
        )
        .join('');

      return `
        <div class="workflow-editor-settings-group">
          ${labelMarkup}
          <select
            id="${escapeHtml(fieldId)}"
            class="form-select workflow-editor-settings-control"
            data-node-setting-key="${escapeHtml(field.key)}"
            data-node-setting-type="${escapeHtml(field.type)}"
          >
            <option value="">${escapeHtml(params.presentation.controls.select_placeholder)}</option>
            ${options}
          </select>
          ${helpText}
          ${fieldPreview}
        </div>
      `;
    }

    return `
      <div class="workflow-editor-settings-group">
        ${labelMarkup}
        <input
          id="${escapeHtml(fieldId)}"
          type="text"
          class="form-control workflow-editor-settings-control"
          value="${escapeHtml(value)}"
          placeholder="${escapeHtml(field.placeholder ?? '')}"
          data-node-setting-key="${escapeHtml(field.key)}"
          data-node-setting-type="${escapeHtml(field.type)}"
        >
        ${helpText}
        ${expressionHint}
        ${fieldPreview}
        ${assistMarkup}
      </div>
    `;
  }

  const inputFields = visibleFields.filter((field) => getTemplateFieldUiGroup(field) === 'input');
  const resultFields = visibleFields.filter((field) => getTemplateFieldUiGroup(field) === 'result');
  const advancedFields = visibleFields.filter((field) => getTemplateFieldUiGroup(field) === 'advanced');

  return [
    renderSettingsSection({
      title: params.presentation.groups.input?.title ?? 'Pass data in',
      description: params.presentation.groups.input?.description ?? '',
      body: inputFields.map((field) => renderSettingsField(field)).join(''),
    }),
    renderSettingsSection({
      title: params.presentation.groups.result?.title ?? 'Save result',
      description: params.presentation.groups.result?.description ?? '',
      body: resultFields.map((field) => renderSettingsField(field)).join(''),
    }),
    renderSettingsSection({
      title: params.presentation.groups.advanced?.title ?? 'Other settings',
      description: params.presentation.groups.advanced?.description ?? '',
      body: advancedFields.map((field) => renderSettingsField(field)).join(''),
    }),
  ]
    .filter((sectionMarkup) => sectionMarkup.length > 0)
    .join('');
}
