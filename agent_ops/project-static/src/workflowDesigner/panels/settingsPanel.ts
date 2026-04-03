import { renderSettingAssistMarkup } from './settingsAssist';
import type {
  WorkflowNode,
  WorkflowNodeDefinition,
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
  nodeDefinitionLabel: string;
  nodeId: string;
}): string {
  return `
    <section class="workflow-editor-settings-section">
      <div class="workflow-editor-settings-section-head">
        <div class="workflow-editor-settings-section-title">Node overview</div>
        <div class="workflow-editor-settings-section-description">Keep the graph readable and make the node’s role obvious at a glance.</div>
      </div>
      <div class="workflow-editor-settings-section-body">
        <div class="workflow-editor-settings-group">
          <div class="workflow-editor-settings-help">Type</div>
          <div class="workflow-editor-settings-preview">${escapeHtml(params.nodeDefinitionLabel)}</div>
        </div>
        <div class="workflow-editor-settings-group">
          <div class="workflow-editor-settings-help">Node id</div>
          <div class="workflow-editor-settings-expression-hint"><code>${escapeHtml(params.nodeId)}</code></div>
        </div>
      </div>
    </section>
  `;
}

export function renderSettingsIdentitySection(params: {
  nodeId: string;
  nodeLabel: string;
}): string {
  return `
    <section class="workflow-editor-settings-section">
      <div class="workflow-editor-settings-section-head">
        <div class="workflow-editor-settings-section-title">Identity</div>
        <div class="workflow-editor-settings-section-description">Rename the node so the graph reads clearly.</div>
      </div>
      <div class="workflow-editor-settings-section-body">
        <div class="workflow-editor-settings-group">
          <label class="form-label" for="workflow-node-label-${escapeHtml(params.nodeId)}">Node name</label>
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
            <div class="workflow-editor-settings-mode-toggle" role="group" aria-label="${escapeHtml(`${field.label} mode`)}">
              <button
                type="button"
                class="workflow-editor-settings-mode-button${fieldInputMode === 'static' ? ' is-active' : ''}"
                data-node-setting-mode-key="${escapeHtml(field.key)}"
                data-node-setting-mode="static"
              >
                Static
              </button>
              <button
                type="button"
                class="workflow-editor-settings-mode-button${fieldInputMode === 'expression' ? ' is-active' : ''}"
                data-node-setting-mode-key="${escapeHtml(field.key)}"
                data-node-setting-mode="expression"
              >
                Expression
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
            Use template syntax like <code>{{ trigger.payload.ticket_id }}</code> or <code>{{ llm.response.text }}</code>.
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
            <option value="">Select</option>
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
      title: 'Pass data in',
      description: 'Choose Static or Expression for each input, then map trigger payload and earlier node outputs.',
      body: inputFields.map((field) => renderSettingsField(field)).join(''),
    }),
    renderSettingsSection({
      title: 'Save result',
      description: 'Choose where this node should read or write workflow context values.',
      body: resultFields.map((field) => renderSettingsField(field)).join(''),
    }),
    renderSettingsSection({
      title: 'Other settings',
      description: 'Provider, routing, and runtime controls for this node.',
      body: advancedFields.map((field) => renderSettingsField(field)).join(''),
    }),
  ]
    .filter((sectionMarkup) => sectionMarkup.length > 0)
    .join('');
}
