import type {
  WorkflowEdge,
  WorkflowNode,
  WorkflowNodeTemplate,
  WorkflowNodeTemplateField,
  WorkflowSpecializedDefinition,
} from './types';
import {
  escapeHtml,
  formatKindLabel,
  getNodeTitle,
  getTemplateFieldValue,
} from './utils';

export function renderSelectedTemplateMarkup(
  node: WorkflowNode | undefined,
  template: WorkflowNodeTemplate | undefined,
): string {
  if (!node) {
    return '';
  }

  const icon = template?.icon ?? 'mdi-vector-square';
  const title = template?.label ?? formatKindLabel(node.kind);
  const description =
    template?.description ??
    'Custom node. Use the advanced runtime JSON editor to configure fields that are not mapped into the inspector.';

  return `
    <div class="workflow-selected-template-card workflow-selected-template-card--compact${template ? '' : ' is-custom'}">
      <span class="workflow-selected-template-icon">
        <i class="mdi ${escapeHtml(icon)}"></i>
      </span>
      <div class="workflow-selected-template-copy">
        <div class="workflow-selected-template-title">${escapeHtml(title)}</div>
        <div class="workflow-selected-template-description">${escapeHtml(description)}</div>
      </div>
    </div>
  `;
}

export function renderFieldMarkup(
  fields: WorkflowNodeTemplateField[],
  node: WorkflowNode,
  nodes: WorkflowNode[],
): string {
  const nodeTargetOptions = nodes
    .filter((candidate) => candidate.id !== node.id)
    .map(
      (candidate) =>
        `<option value="${escapeHtml(candidate.id)}">${escapeHtml(getNodeTitle(candidate))}</option>`,
    )
    .join('');

  return fields
    .map((field) => {
      const fieldValue = getTemplateFieldValue(node, field);
      const currentValue = escapeHtml(fieldValue);
      const helpText = field.help_text
        ? `<div class="form-hint">${escapeHtml(field.help_text)}</div>`
        : '';

      if (field.type === 'textarea') {
        return `
          <div>
            <label class="form-label" for="workflow-config-${escapeHtml(field.key)}">${escapeHtml(field.label)}</label>
            <textarea
              id="workflow-config-${escapeHtml(field.key)}"
              class="form-control"
              rows="${field.rows ?? 4}"
              placeholder="${escapeHtml(field.placeholder ?? '')}"
              data-config-field="${escapeHtml(field.key)}"
            >${currentValue}</textarea>
            ${helpText}
          </div>
        `;
      }

      if (field.type === 'select') {
        const options = (field.options ?? [])
          .map((option) => {
            const selected = option.value === fieldValue ? ' selected' : '';
            return `<option value="${escapeHtml(option.value)}"${selected}>${escapeHtml(option.label)}</option>`;
          })
          .join('');

        return `
          <div>
            <label class="form-label" for="workflow-config-${escapeHtml(field.key)}">${escapeHtml(field.label)}</label>
            <select
              id="workflow-config-${escapeHtml(field.key)}"
              class="form-select"
              data-config-field="${escapeHtml(field.key)}"
            >
              ${options}
            </select>
            ${helpText}
          </div>
        `;
      }

      if (field.type === 'node_target') {
        return `
          <div>
            <label class="form-label" for="workflow-config-${escapeHtml(field.key)}">${escapeHtml(field.label)}</label>
            <select
              id="workflow-config-${escapeHtml(field.key)}"
              class="form-select"
              data-config-field="${escapeHtml(field.key)}"
            >
              <option value="">Choose a connected node</option>
              ${nodeTargetOptions}
            </select>
            ${helpText}
          </div>
        `;
      }

      return `
        <div>
          <label class="form-label" for="workflow-config-${escapeHtml(field.key)}">${escapeHtml(field.label)}</label>
          <input
            id="workflow-config-${escapeHtml(field.key)}"
            class="form-control"
            type="text"
            value="${currentValue}"
            placeholder="${escapeHtml(field.placeholder ?? '')}"
            data-config-field="${escapeHtml(field.key)}"
          >
          ${helpText}
        </div>
      `;
    })
    .join('');
}

export function renderTemplateFieldsMarkup(params: {
  node: WorkflowNode;
  nodes: WorkflowNode[];
  specializedDefinition?: WorkflowSpecializedDefinition;
  template: WorkflowNodeTemplate;
}): string {
  const { node, nodes, specializedDefinition, template } = params;
  const specializedSection =
    node.kind === 'tool' || node.kind === 'trigger'
      ? specializedDefinition
        ? `
          <div class="workflow-selected-template-card workflow-tool-definition-card mt-3">
            <span class="workflow-selected-template-icon">
              <i class="mdi ${escapeHtml(specializedDefinition.icon ?? 'mdi-tools')}"></i>
            </span>
            <div class="workflow-selected-template-copy">
              <div class="workflow-selected-template-title">${escapeHtml(specializedDefinition.label)}</div>
              <div class="workflow-selected-template-description">${escapeHtml(specializedDefinition.description)}</div>
            </div>
          </div>
          <div class="stack-sm mt-3">
            ${renderFieldMarkup(specializedDefinition.fields, node, nodes)}
          </div>
        `
        : `
          <div class="workflow-empty-copy mt-3">
            Choose a ${node.kind === 'tool' ? 'tool' : 'trigger'} definition to configure its fields.
          </div>
        `
      : '';

  return `
    <div class="stack-sm">
      ${renderFieldMarkup(template.fields, node, nodes)}
    </div>
    ${specializedSection}
  `;
}

export function renderQuickAddMenuMarkup(
  sourceId: string,
  templates: WorkflowNodeTemplate[],
): string {
  const items = templates
    .map(
      (template) => `
        <button
          type="button"
          class="workflow-node-quick-add-item"
          data-quick-add-kind="${escapeHtml(template.kind)}"
          data-quick-add-source="${escapeHtml(sourceId)}"
        >
          <span class="workflow-node-quick-add-item-icon">
            <i class="mdi ${escapeHtml(template.icon ?? 'mdi-vector-square')}"></i>
          </span>
          <span class="workflow-node-quick-add-item-copy">
            <span class="workflow-node-quick-add-item-title">${escapeHtml(template.label)}</span>
            <span class="workflow-node-quick-add-item-description">${escapeHtml(template.description)}</span>
          </span>
        </button>
      `,
    )
    .join('');

  return `
    <div class="workflow-node-quick-add-menu" data-quick-add-menu="${escapeHtml(sourceId)}">
      <div class="workflow-node-quick-add-header">
        <i class="mdi mdi-magnify"></i>
        <span>Add next step</span>
      </div>
      <div class="workflow-node-quick-add-list">${items}</div>
    </div>
  `;
}

export function renderNodeMarkup(params: {
  isDisabled: boolean;
  isRunning: boolean;
  isSelected: boolean;
  node: WorkflowNode;
  quickAddMenuMarkup: string;
  showQuickAddMenu: boolean;
  statusLabel: string;
  subtitle: string;
  template?: WorkflowNodeTemplate;
}): string {
  const {
    isDisabled,
    isRunning,
    isSelected,
    node,
    quickAddMenuMarkup,
    showQuickAddMenu,
    statusLabel,
    subtitle,
    template,
  } = params;

  return `
    <span class="workflow-node-port workflow-node-port--input" data-port-input="${escapeHtml(node.id)}" aria-label="Connect into ${escapeHtml(getNodeTitle(node))}"></span>
    <span class="workflow-node-port workflow-node-port--output" data-port-output="${escapeHtml(node.id)}" aria-label="Connect from ${escapeHtml(getNodeTitle(node))}"></span>
    ${
      isSelected
        ? `
          <div class="workflow-node-toolbar" data-node-toolbar="${escapeHtml(node.id)}">
            <button type="button" class="workflow-node-toolbar-button" data-node-action="run" data-node-action-id="${escapeHtml(node.id)}" aria-label="Run node">
              <i class="mdi mdi-play"></i>
            </button>
            <button type="button" class="workflow-node-toolbar-button" data-node-action="toggle-disabled" data-node-action-id="${escapeHtml(node.id)}" aria-label="Toggle node state">
              <i class="mdi ${isDisabled ? 'mdi-power-plug-off-outline' : 'mdi-power'}"></i>
            </button>
            <button type="button" class="workflow-node-toolbar-button" data-node-action="delete" data-node-action-id="${escapeHtml(node.id)}" aria-label="Delete node">
              <i class="mdi mdi-trash-can-outline"></i>
            </button>
            <button type="button" class="workflow-node-toolbar-button" data-node-action="more" data-node-action-id="${escapeHtml(node.id)}" aria-label="More options">
              <i class="mdi mdi-dots-horizontal"></i>
            </button>
          </div>
        `
        : ''
    }
    <div class="workflow-node-body" data-node-body="${escapeHtml(node.id)}">
      <div class="workflow-node-accent" aria-hidden="true"></div>
      <div class="workflow-node-header">
        <span class="workflow-node-meta">
          <span class="workflow-node-icon">
            <i class="mdi ${escapeHtml(template?.icon ?? 'mdi-vector-square')}"></i>
          </span>
          <span class="workflow-node-copy">
            <strong class="workflow-node-title">${escapeHtml(getNodeTitle(node))}</strong>
            <span class="workflow-node-subtitle">${escapeHtml(subtitle)}</span>
          </span>
        </span>
        <span class="workflow-node-status">
          <span class="workflow-node-status-dot" aria-hidden="true"></span>
          ${escapeHtml(statusLabel)}
        </span>
      </div>
      <div class="workflow-node-footer">
        <span class="workflow-node-kind">${escapeHtml(formatKindLabel(node.kind))}</span>
        ${
          isSelected
            ? `
              <button type="button" class="workflow-node-add-next" data-quick-add-toggle="${escapeHtml(node.id)}" aria-label="Add next node">
                <i class="mdi mdi-plus"></i>
              </button>
            `
            : ''
        }
      </div>
    </div>
    ${showQuickAddMenu ? quickAddMenuMarkup : ''}
  `;
}

export function renderEdgeListMarkup(params: {
  edges: WorkflowEdge[];
  getNodeById: (nodeId: string) => WorkflowNode | undefined;
}): string {
  const { edges, getNodeById } = params;

  return edges
    .map((edge) => {
      const source = getNodeById(edge.source);
      const target = getNodeById(edge.target);
      const sourceLabel = source ? getNodeTitle(source) : edge.source;
      const targetLabel = target ? getNodeTitle(target) : edge.target;

      return `
        <div class="workflow-edge-item">
          <div class="workflow-edge-copy">
            <span class="workflow-edge-terminal">
              <span class="workflow-edge-terminal-label">Source</span>
              <strong class="workflow-edge-terminal-value">${escapeHtml(sourceLabel)}</strong>
            </span>
            <span class="workflow-edge-arrow" aria-hidden="true">
              <i class="mdi mdi-arrow-right"></i>
            </span>
            <span class="workflow-edge-terminal">
              <span class="workflow-edge-terminal-label">Target</span>
              <strong class="workflow-edge-terminal-value">${escapeHtml(targetLabel)}</strong>
            </span>
          </div>
          <button type="button" class="btn btn-outline-danger btn-sm" data-remove-edge="${escapeHtml(edge.id)}">
            Remove
          </button>
        </div>
      `;
    })
    .join('');
}
