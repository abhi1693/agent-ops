import type {
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowSettingsPresentation,
  WorkflowNodeTemplateField,
  WorkflowNodeTemplateOption,
} from '../../types';
import { isWebhookTriggerDefinition } from '../../registry/nodeSemantics';
import { escapeHtml } from '../../utils';
import {
  getConfigString,
  getTemplateFieldInputMode,
  getTemplateFieldUiGroup,
  getTemplateFieldValue,
  getTemplateFieldValueAtPath,
  isTemplateFieldVisible,
  supportsTemplateFieldInputMode,
} from '../../utils';
import { renderSettingsSection } from './settingsSection';
import {
  renderFieldHelpText,
  renderFieldLabelMarkup,
  renderRequiredBadge,
} from './settingsShared';

function getRenderedFieldValue(field: WorkflowNodeTemplateField, value: string): string {
  if (field.type !== 'datetime' || !value) {
    return value;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  const year = parsed.getFullYear();
  const month = `${parsed.getMonth() + 1}`.padStart(2, '0');
  const day = `${parsed.getDate()}`.padStart(2, '0');
  const hours = `${parsed.getHours()}`.padStart(2, '0');
  const minutes = `${parsed.getMinutes()}`.padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function renderWebhookTriggerSection(params: {
  node: WorkflowNode;
  nodeDefinition: WorkflowNodeDefinition;
  webhookUrl?: string;
}): string {
  if (!isWebhookTriggerDefinition(params.nodeDefinition) || !params.webhookUrl) {
    return '';
  }

  const method = getConfigString(params.node.config, 'http_method') || 'POST';
  const configuredPath = (getConfigString(params.node.config, 'path') || '')
    .trim()
    .replace(/^\/+|\/+$/g, '')
    .split('/')
    .filter(Boolean)
    .join('/');
  let endpointUrl = params.webhookUrl;
  if (configuredPath) {
    try {
      const parsedUrl = new URL(params.webhookUrl, window.location.origin);
      const basePathname = parsedUrl.pathname.replace(/\/+$/, '');
      parsedUrl.pathname = `${basePathname}/${configuredPath}`;
      endpointUrl = parsedUrl.toString();
    } catch (_error) {
      endpointUrl = `${params.webhookUrl.replace(/\/+$/, '')}/${configuredPath}`;
    }
  }

  return renderSettingsSection({
    title: 'Webhook URL',
    description: '',
    body: `
      <div class="workflow-editor-settings-group">
        <div class="workflow-editor-settings-label-row">
          <label class="form-label" for="workflow-node-webhook-url-${escapeHtml(params.node.id)}">Endpoint</label>
          <span class="badge text-bg-secondary">${escapeHtml(method)}</span>
        </div>
        <input
          id="workflow-node-webhook-url-${escapeHtml(params.node.id)}"
          type="text"
          class="form-control workflow-editor-settings-control"
          value="${escapeHtml(endpointUrl)}"
          title="Click to copy"
          data-webhook-endpoint-copy="true"
          readonly
        >
      </div>
    `,
  });
}

function renderNestedFieldControl(params: {
  field: WorkflowNodeTemplateField;
  fieldId: string;
  path: string;
  presentation: WorkflowSettingsPresentation;
  value: string;
  options: WorkflowNodeTemplateOption[];
}): string {
  const { field, fieldId, path, presentation, value, options } = params;
  const valueTypeAttribute = field.value_type
    ? ` data-node-setting-value-type="${escapeHtml(field.value_type)}"`
    : '';
  const inputType = field.type === 'datetime' ? 'datetime-local' : 'text';
  const renderedValue = getRenderedFieldValue(field, value);

  if (field.type === 'textarea') {
    return `
      <textarea
        id="${escapeHtml(fieldId)}"
        class="form-control workflow-editor-settings-control"
        rows="${field.rows ?? 4}"
        data-node-setting-path="${escapeHtml(path)}"
        data-node-setting-type="${escapeHtml(field.type)}"${valueTypeAttribute}
      >${escapeHtml(value)}</textarea>
    `;
  }

  if (field.type === 'select' || field.type === 'node_target') {
    const optionsMarkup = options
      .map(
        (option) => `
          <option value="${escapeHtml(option.value)}"${option.value === value ? ' selected' : ''}>
            ${escapeHtml(option.label)}
          </option>
        `,
      )
      .join('');

    return `
      <select
        id="${escapeHtml(fieldId)}"
        class="form-select workflow-editor-settings-control"
        data-node-setting-path="${escapeHtml(path)}"
        data-node-setting-type="${escapeHtml(field.type)}"${valueTypeAttribute}
      >
        <option value="">${escapeHtml(presentation.controls.select_placeholder)}</option>
        ${optionsMarkup}
      </select>
    `;
  }

  return `
    <input
      id="${escapeHtml(fieldId)}"
      type="${escapeHtml(inputType)}"
      class="form-control workflow-editor-settings-control"
      value="${escapeHtml(renderedValue)}"
      placeholder="${escapeHtml(field.placeholder ?? '')}"
      data-node-setting-path="${escapeHtml(path)}"
      data-node-setting-type="${escapeHtml(field.type)}"${valueTypeAttribute}
    >
  `;
}

function renderCollectionField(params: {
  field: WorkflowNodeTemplateField;
  getNodeTargetOptions: () => Array<{ label: string; value: string }>;
  node: WorkflowNode;
  presentation: WorkflowSettingsPresentation;
}): string {
  const { field, getNodeTargetOptions, node, presentation } = params;
  const fieldId = `workflow-node-setting-${node.id}-${field.key}`;
  const labelMarkup = renderRequiredBadge({
    badgeText: presentation.controls.required_badge,
    fieldId,
    isRequired: field.required,
    label: field.label,
  });
  const collectionOptions = field.collection_options ?? [];
  const currentValue =
    node.config[field.key] && typeof node.config[field.key] === 'object' && !Array.isArray(node.config[field.key])
      ? (node.config[field.key] as Record<string, unknown>)
      : {};

  const optionMarkup = collectionOptions
    .map((option) => {
      const rawItems = currentValue[option.key];
      const items = Array.isArray(rawItems) ? rawItems : [];
      const renderedItems = items
        .map((item, itemIndex) => {
          const itemValue = item && typeof item === 'object' && !Array.isArray(item)
            ? (item as Record<string, unknown>)
            : {};
          const visibleNestedFields = option.fields.filter((nestedField) => {
            if (!nestedField.visible_when) {
              return true;
            }
            return Object.entries(nestedField.visible_when).every(([configKey, allowedValues]) => {
              const currentNestedValue = getConfigString(itemValue, configKey, nestedField.type === 'textarea');
              return allowedValues.includes(currentNestedValue);
            });
          });
          const titleField = itemValue.name;
          const itemTitle = typeof titleField === 'string' && titleField.trim()
            ? titleField.trim()
            : `${option.label} ${itemIndex + 1}`;

          const nestedMarkup = visibleNestedFields
            .map((nestedField) => {
              const nestedPath = `${field.key}.${option.key}.${itemIndex}.${nestedField.key}`;
              const nestedFieldId = `${fieldId}-${option.key}-${itemIndex}-${nestedField.key}`;
              const nestedValue = getTemplateFieldValueAtPath(
                node,
                nestedPath,
                nestedField.type === 'textarea',
              );
              const nestedOptions = nestedField.type === 'node_target'
                ? getNodeTargetOptions()
                : nestedField.options ?? [];

              return `
                <div class="workflow-editor-settings-group">
                  ${renderRequiredBadge({
                    badgeText: presentation.controls.required_badge,
                    fieldId: nestedFieldId,
                    isRequired: nestedField.required,
                    label: nestedField.label,
                  })}
                  ${renderNestedFieldControl({
                    field: nestedField,
                    fieldId: nestedFieldId,
                    path: nestedPath,
                    presentation,
                    value: nestedValue,
                    options: nestedOptions,
                  })}
                  ${renderFieldHelpText(nestedField.help_text)}
                </div>
              `;
            })
            .join('');

          const itemActions = `
            <div class="workflow-editor-settings-action-row">
              <button
                type="button"
                class="btn btn-sm btn-outline-secondary"
                data-node-setting-collection-remove="true"
                data-node-setting-collection-field="${escapeHtml(field.key)}"
                data-node-setting-collection-option="${escapeHtml(option.key)}"
                data-node-setting-collection-index="${itemIndex}"
              >
                Remove
              </button>
            </div>
          `;

          return renderSettingsSection({
            title: itemTitle,
            description: '',
            body: `${itemActions}${nestedMarkup}`,
          });
        })
        .join('');

      return `
        <div class="workflow-editor-settings-group">
          ${renderFieldHelpText(option.description)}
          ${renderedItems}
          <div class="workflow-editor-settings-action-row">
            <button
              type="button"
              class="btn btn-sm btn-outline-secondary"
              data-node-setting-collection-add="true"
              data-node-setting-collection-field="${escapeHtml(field.key)}"
              data-node-setting-collection-option="${escapeHtml(option.key)}"
            >
              Add ${escapeHtml(option.label)}
            </button>
          </div>
        </div>
      `;
    })
    .join('');

  return `
    <div class="workflow-editor-settings-group">
      ${labelMarkup}
      ${renderFieldHelpText(field.help_text)}
      ${optionMarkup || `<div class="workflow-editor-settings-empty">${escapeHtml(field.description ?? 'No items configured yet.')}</div>`}
    </div>
  `;
}

function renderSettingsField(params: {
  field: WorkflowNodeTemplateField;
  getFieldOptions: (field: WorkflowNodeTemplateField) => WorkflowNodeTemplateOption[];
  getNodeTargetOptions: () => Array<{ label: string; value: string }>;
  node: WorkflowNode;
  presentation: WorkflowSettingsPresentation;
}): string {
  const { field, getFieldOptions, getNodeTargetOptions, node, presentation } = params;
  if (field.type === 'fixed_collection') {
    return renderCollectionField({
      field,
      getNodeTargetOptions,
      node,
      presentation,
    });
  }

  const fieldId = `workflow-node-setting-${node.id}-${field.key}`;
  const value = getTemplateFieldValue(node, field);
  const supportsInputMode = supportsTemplateFieldInputMode(field);
  const fieldInputMode = getTemplateFieldInputMode(node, field);
  const labelMarkup = renderFieldLabelMarkup({
    field,
    fieldId,
    fieldInputMode,
    presentation,
    supportsInputMode,
  });
  const helpText = renderFieldHelpText(field.help_text);
  const expressionHint = supportsInputMode && fieldInputMode === 'expression'
    ? `
        <div class="workflow-editor-settings-expression-hint">
          ${escapeHtml(presentation.controls.expression_hint)}
        </div>
      `
    : '';
  const valueTypeAttribute = field.value_type
    ? ` data-node-setting-value-type="${escapeHtml(field.value_type)}"`
    : '';
  const inputType = field.type === 'datetime' ? 'datetime-local' : 'text';
  const renderedValue = getRenderedFieldValue(field, value);

  if (field.type === 'textarea') {
    return `
      <div class="workflow-editor-settings-group">
        ${labelMarkup}
        <textarea
          id="${escapeHtml(fieldId)}"
          class="form-control workflow-editor-settings-control"
          rows="${field.rows ?? 4}"
          data-node-setting-key="${escapeHtml(field.key)}"
          data-node-setting-type="${escapeHtml(field.type)}"${valueTypeAttribute}
        >${escapeHtml(value)}</textarea>
        ${helpText}
        ${expressionHint}
      </div>
    `;
  }

  if (field.type === 'select' || field.type === 'node_target') {
    const options = (field.type === 'node_target'
      ? getNodeTargetOptions()
      : getFieldOptions(field)
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
          data-node-setting-type="${escapeHtml(field.type)}"${valueTypeAttribute}
        >
          <option value="">${escapeHtml(presentation.controls.select_placeholder)}</option>
          ${options}
        </select>
        ${helpText}
      </div>
    `;
  }

  return `
    <div class="workflow-editor-settings-group">
      ${labelMarkup}
      <input
        id="${escapeHtml(fieldId)}"
        type="${escapeHtml(inputType)}"
        class="form-control workflow-editor-settings-control"
        value="${escapeHtml(renderedValue)}"
        placeholder="${escapeHtml(field.placeholder ?? '')}"
        data-node-setting-key="${escapeHtml(field.key)}"
        data-node-setting-type="${escapeHtml(field.type)}"${valueTypeAttribute}
      >
      ${helpText}
      ${expressionHint}
    </div>
  `;
}

export function renderNodeSettingsFieldsMarkup(params: {
  availableInputPaths: string[];
  getFieldOptions: (field: WorkflowNodeTemplateField) => WorkflowNodeTemplateOption[];
  getNodeTargetOptions: () => Array<{ label: string; value: string }>;
  node: WorkflowNode;
  nodeDefinition: WorkflowNodeDefinition;
  presentation: WorkflowSettingsPresentation;
  webhookUrl?: string;
}): string {
  const visibleFields = params.nodeDefinition.fields.filter((field) => isTemplateFieldVisible(params.node, field));
  const renderField = (field: WorkflowNodeTemplateField): string =>
    renderSettingsField({
      field,
      getFieldOptions: params.getFieldOptions,
      getNodeTargetOptions: params.getNodeTargetOptions,
      node: params.node,
      presentation: params.presentation,
    });

  const inputFields = visibleFields.filter((field) => getTemplateFieldUiGroup(field) === 'input');
  const resultFields = visibleFields.filter((field) => getTemplateFieldUiGroup(field) === 'result');
  const advancedFields = visibleFields.filter((field) => getTemplateFieldUiGroup(field) === 'advanced');

  return [
    renderWebhookTriggerSection({
      node: params.node,
      nodeDefinition: params.nodeDefinition,
      webhookUrl: params.webhookUrl,
    }),
    renderSettingsSection({
      title: params.presentation.groups.input?.title ?? 'Pass data in',
      description: params.presentation.groups.input?.description ?? '',
      body: inputFields.map(renderField).join(''),
    }),
    renderSettingsSection({
      title: params.presentation.groups.result?.title ?? 'Save result',
      description: params.presentation.groups.result?.description ?? '',
      body: resultFields.map(renderField).join(''),
    }),
    renderSettingsSection({
      title: params.presentation.groups.advanced?.title ?? 'Other settings',
      description: params.presentation.groups.advanced?.description ?? '',
      body: advancedFields.map(renderField).join(''),
    }),
  ]
    .filter((sectionMarkup) => sectionMarkup.length > 0)
    .join('');
}
