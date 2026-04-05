import type {
  WorkflowConnection,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowSettingsPresentation,
  WorkflowNodeTemplateField,
  WorkflowNodeTemplateOption,
} from '../types';
import { escapeHtml } from '../utils';
import {
  getConfigString,
  getTemplateFieldBinding,
  getTemplateFieldInputMode,
  getTemplateFieldUiGroup,
  getTemplateFieldValue,
  getTemplateFieldValueAtPath,
  isTemplateFieldVisible,
  supportsTemplateFieldInputMode,
} from '../utils';

function renderRequiredBadge(params: {
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

function renderFieldLabelMarkup(params: {
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
        ${params.description.trim()
          ? `<div class="workflow-editor-settings-section-description">${escapeHtml(params.description)}</div>`
          : ''}
      </div>
      <div class="workflow-editor-settings-section-body">
        ${params.body}
      </div>
    </section>
  `;
}

function renderWebhookTriggerSection(params: {
  node: WorkflowNode;
  nodeDefinition: WorkflowNodeDefinition;
  webhookUrl?: string;
}): string {
  if (params.nodeDefinition.type !== 'core.webhook_trigger' || !params.webhookUrl) {
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
        ${overviewPresentation.description.trim()
          ? `<div class="workflow-editor-settings-section-description">${escapeHtml(overviewPresentation.description)}</div>`
          : ''}
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
        ${identityPresentation.description.trim()
          ? `<div class="workflow-editor-settings-section-description">${escapeHtml(identityPresentation.description)}</div>`
          : ''}
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
  webhookUrl?: string;
}): string {
  const visibleFields = params.nodeDefinition.fields.filter((field) => isTemplateFieldVisible(params.node, field));

  function renderFieldHelpMarkup(field: WorkflowNodeTemplateField): string {
    return field.help_text
      ? `<div class="workflow-editor-settings-help">${escapeHtml(field.help_text)}</div>`
      : '';
  }

  function renderNestedField(paramsForField: {
    field: WorkflowNodeTemplateField;
    fieldId: string;
    path: string;
    value: string;
    options: WorkflowNodeTemplateOption[];
  }): string {
    const { field, fieldId, path, value, options } = paramsForField;
    const valueTypeAttribute = field.value_type
      ? ` data-node-setting-value-type="${escapeHtml(field.value_type)}"`
      : '';

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
          <option value="">${escapeHtml(params.presentation.controls.select_placeholder)}</option>
          ${optionsMarkup}
        </select>
      `;
    }

    return `
      <input
        id="${escapeHtml(fieldId)}"
        type="text"
        class="form-control workflow-editor-settings-control"
        value="${escapeHtml(value)}"
        placeholder="${escapeHtml(field.placeholder ?? '')}"
        data-node-setting-path="${escapeHtml(path)}"
        data-node-setting-type="${escapeHtml(field.type)}"${valueTypeAttribute}
      >
    `;
  }

  function renderCollectionField(field: WorkflowNodeTemplateField): string {
    const fieldId = `workflow-node-setting-${params.node.id}-${field.key}`;
    const labelMarkup = renderRequiredBadge({
      badgeText: params.presentation.controls.required_badge,
      fieldId,
      isRequired: field.required,
      label: field.label,
    });
    const collectionOptions = field.collection_options ?? [];
    const currentValue =
      params.node.config[field.key] && typeof params.node.config[field.key] === 'object' && !Array.isArray(params.node.config[field.key])
        ? (params.node.config[field.key] as Record<string, unknown>)
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
                  params.node,
                  nestedPath,
                  nestedField.type === 'textarea',
                );
                const nestedOptions = nestedField.type === 'node_target'
                  ? params.getNodeTargetOptions()
                  : nestedField.options ?? [];

                return `
                  <div class="workflow-editor-settings-group">
                    ${renderRequiredBadge({
                      badgeText: params.presentation.controls.required_badge,
                      fieldId: nestedFieldId,
                      isRequired: nestedField.required,
                      label: nestedField.label,
                    })}
                    ${renderNestedField({
                      field: nestedField,
                      fieldId: nestedFieldId,
                      path: nestedPath,
                      value: nestedValue,
                      options: nestedOptions,
                    })}
                    ${renderFieldHelpMarkup(nestedField)}
                  </div>
                `;
              })
              .join('');

            return `
              <div class="workflow-editor-settings-section">
                <div class="workflow-editor-settings-section-head">
                  <div class="workflow-editor-settings-section-title">${escapeHtml(itemTitle)}</div>
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
                </div>
                <div class="workflow-editor-settings-section-body">
                  ${nestedMarkup}
                </div>
              </div>
            `;
          })
          .join('');

        return `
          <div class="workflow-editor-settings-group">
            ${
              option.description
                ? `<div class="workflow-editor-settings-help">${escapeHtml(option.description)}</div>`
                : ''
            }
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
        ${renderFieldHelpMarkup(field)}
        ${optionMarkup || `<div class="workflow-editor-settings-empty">${escapeHtml(field.description ?? 'No items configured yet.')}</div>`}
      </div>
    `;
  }

  function renderSettingsField(field: WorkflowNodeTemplateField): string {
    if (field.type === 'fixed_collection') {
      return renderCollectionField(field);
    }

    const fieldId = `workflow-node-setting-${params.node.id}-${field.key}`;
    const value = getTemplateFieldValue(params.node, field);
    const supportsInputMode = supportsTemplateFieldInputMode(field);
    const fieldInputMode = getTemplateFieldInputMode(params.node, field);
    const labelMarkup = renderFieldLabelMarkup({
      field,
      fieldId,
      fieldInputMode,
      presentation: params.presentation,
      supportsInputMode,
    });
    const helpText = renderFieldHelpMarkup(field);
    const expressionHint = supportsInputMode && fieldInputMode === 'expression'
      ? `
          <div class="workflow-editor-settings-expression-hint">
            ${escapeHtml(params.presentation.controls.expression_hint)}
          </div>
        `
      : '';
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
            ${field.value_type ? `data-node-setting-value-type="${escapeHtml(field.value_type)}"` : ''}
          >${escapeHtml(value)}</textarea>
          ${helpText}
          ${expressionHint}
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
            ${field.value_type ? `data-node-setting-value-type="${escapeHtml(field.value_type)}"` : ''}
          >
            <option value="">${escapeHtml(params.presentation.controls.select_placeholder)}</option>
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
          type="text"
          class="form-control workflow-editor-settings-control"
          value="${escapeHtml(value)}"
          placeholder="${escapeHtml(field.placeholder ?? '')}"
          data-node-setting-key="${escapeHtml(field.key)}"
          data-node-setting-type="${escapeHtml(field.type)}"
          ${field.value_type ? `data-node-setting-value-type="${escapeHtml(field.value_type)}"` : ''}
        >
        ${helpText}
        ${expressionHint}
      </div>
    `;
  }

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

export function renderNodeConnectionSection(params: {
  connectionCreateUrl?: string | null;
  connections: WorkflowConnection[];
  node: WorkflowNode;
  nodeDefinition: WorkflowNodeDefinition;
  presentation: WorkflowSettingsPresentation;
}): string {
  const connectionSlots = params.nodeDefinition.connection_slots ?? [];
  if (connectionSlots.length === 0) {
    return '';
  }

  const connectionPresentation = params.presentation.groups.connection;
  const body = connectionSlots
    .map((slot) => {
      const fieldId = `workflow-node-connection-${params.node.id}-${slot.key}`;
      const currentValue = getConfigString(params.node.config, slot.key);
      const compatibleConnections = params.connections.filter(
        (connection) => slot.allowed_connection_types.includes(connection.connection_type),
      );
      const selectableConnections = compatibleConnections.filter((connection) => connection.enabled);
      const currentConnection = compatibleConnections.find((connection) => String(connection.id) === currentValue);
      const options = selectableConnections.map((connection) => {
        const scopeSuffix = connection.scope_label ? ` · ${connection.scope_label}` : '';
        return {
          label: `${connection.label}${scopeSuffix}`,
          value: String(connection.id),
        };
      });

      if (currentValue && !options.some((option) => option.value === currentValue)) {
        options.unshift({
          label: currentConnection
            ? `${currentConnection.label} · unavailable`
            : `Current selection (${currentValue})`,
          value: currentValue,
        });
      }

      const allowedTypes = slot.allowed_connection_types.join(', ');
      const previewParts: string[] = [];
      if (slot.required) {
        previewParts.push('This node needs a compatible connection.');
      }
      if (allowedTypes) {
        previewParts.push(`Allowed types: ${allowedTypes}`);
      }
      if (selectableConnections.length === 0) {
        previewParts.push('No enabled compatible connections are available yet.');
      }
      if (currentConnection?.supports_oauth) {
        previewParts.push(
          currentConnection.oauth_connected
            ? 'OAuth account connected.'
            : 'OAuth authorization still needs to be completed.',
        );
      }

      const actionButtons: string[] = [];
      if (params.connectionCreateUrl) {
        actionButtons.push(`
          <button
            type="button"
            class="btn btn-sm btn-outline-secondary"
            data-workflow-connection-create="${escapeHtml(params.connectionCreateUrl)}"
            data-workflow-connection-default-type="${escapeHtml(slot.allowed_connection_types[0] ?? '')}"
          >
            New
          </button>
        `);
      }
      if (currentConnection?.edit_url) {
        actionButtons.push(`
          <button
            type="button"
            class="btn btn-sm btn-outline-secondary"
            data-workflow-connection-edit="${escapeHtml(currentConnection.edit_url)}"
          >
            Edit
          </button>
        `);
      }
      if (currentConnection?.supports_oauth && currentConnection.oauth_connect_url) {
        actionButtons.push(`
          <button
            type="button"
            class="btn btn-sm btn-primary"
            data-workflow-connection-oauth="${escapeHtml(currentConnection.oauth_connect_url)}"
          >
            ${escapeHtml(currentConnection.oauth_connected ? 'Reconnect' : 'Connect my account')}
          </button>
        `);
      }

      return `
        <div class="workflow-editor-settings-group">
          ${renderRequiredBadge({
            badgeText: params.presentation.controls.required_badge,
            fieldId,
            isRequired: slot.required,
            label: slot.label,
          })}
          <select
            id="${escapeHtml(fieldId)}"
            class="form-select workflow-editor-settings-control"
            data-node-setting-key="${escapeHtml(slot.key)}"
            data-node-setting-type="select"
          >
            <option value="">${escapeHtml(params.presentation.controls.select_placeholder)}</option>
            ${options
              .map(
                (option) => `
                  <option value="${escapeHtml(option.value)}"${option.value === currentValue ? ' selected' : ''}>
                    ${escapeHtml(option.label)}
                  </option>
                `,
              )
              .join('')}
          </select>
          ${slot.description ? `<div class="workflow-editor-settings-help">${escapeHtml(slot.description)}</div>` : ''}
          ${previewParts.length > 0 ? `<div class="workflow-editor-settings-preview">${escapeHtml(previewParts.join(' '))}</div>` : ''}
          ${actionButtons.length > 0 ? `<div class="workflow-editor-settings-action-row">${actionButtons.join('')}</div>` : ''}
        </div>
      `;
    })
    .join('');

  return renderSettingsSection({
    body,
    description: connectionPresentation?.description ?? '',
    title: connectionPresentation?.title ?? 'Connection',
  });
}
