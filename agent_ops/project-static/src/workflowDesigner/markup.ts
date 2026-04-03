import type {
  AgentAuxiliaryPortId,
  ConnectorSide,
  WorkflowEdge,
  WorkflowNodeDefinition,
  WorkflowNode,
  WorkflowNodeTemplateField,
  WorkflowPaletteSection,
} from './types';
import {
  escapeHtml,
  formatKindLabel,
  getTemplateFieldOptions,
  isTemplateFieldVisible,
  getNodeTitle,
  getTemplateFieldValue,
} from './utils';

export function renderSelectedTemplateMarkup(
  node: WorkflowNode | undefined,
  template: WorkflowNodeDefinition | undefined,
): string {
  if (!node) {
    return '';
  }

  const icon = template?.icon ?? 'mdi-vector-square';
  const title = template?.label ?? formatKindLabel(node.kind);
  const description =
    template?.description ??
    'Unsupported node type. Replace it with a supported template before saving this workflow.';

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
      if (!isTemplateFieldVisible(node, field)) {
        return '';
      }

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
        const options = getTemplateFieldOptions(node, field)
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
  template: WorkflowNodeDefinition;
}): string {
  const { node, nodes, template } = params;

  return `
    <div class="stack-sm">
      ${renderFieldMarkup(template.fields, node, nodes)}
    </div>
  `;
}

export function renderQuickAddMenuMarkup(
  sourceId: string,
  templates: WorkflowNodeDefinition[],
): string {
  const items = templates
    .map(
      (template) => `
        <button
          type="button"
          class="workflow-node-quick-add-item"
          data-quick-add-kind="${escapeHtml(template.type)}"
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
  template?: WorkflowNodeDefinition;
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

export function renderNodeContextMenuMarkup(params: {
  meta: string;
  title: string;
}): string {
  return `
    <div class="workflow-editor-node-menu-sheet">
      <div class="workflow-editor-node-menu-head">
        <div class="workflow-editor-node-menu-title">${escapeHtml(params.title)}</div>
        ${params.meta ? `<div class="workflow-editor-node-menu-meta">${escapeHtml(params.meta)}</div>` : ''}
      </div>
      <div class="workflow-editor-node-menu-divider" aria-hidden="true"></div>
      <button
        type="button"
        class="workflow-editor-node-menu-action"
        data-node-menu-action="settings"
      >
        <span class="workflow-editor-node-menu-action-icon" aria-hidden="true">
          <i class="mdi mdi-tune-variant"></i>
        </span>
        <span class="workflow-editor-node-menu-action-label">Settings</span>
      </button>
      <button
        type="button"
        class="workflow-editor-node-menu-action is-danger"
        data-node-menu-action="delete"
      >
        <span class="workflow-editor-node-menu-action-icon" aria-hidden="true">
          <i class="mdi mdi-trash-can-outline"></i>
        </span>
        <span class="workflow-editor-node-menu-action-label">Delete</span>
        <span class="workflow-editor-node-menu-action-shortcut" aria-hidden="true">Del</span>
      </button>
    </div>
  `;
}

export function renderEdgeRemoveButtonMarkup(params: {
  edgeId: string;
  x: number;
  y: number;
}): string {
  return `
    <button
      type="button"
      class="workflow-editor-edge-remove"
      data-remove-edge="${escapeHtml(params.edgeId)}"
      style="left: ${params.x}px; top: ${params.y}px;"
      aria-label="Remove connection"
    >
      <i class="mdi mdi-close"></i>
    </button>
  `;
}

type WorkflowEditorNodeConnector = {
  isCandidate: boolean;
  isInputActive: boolean;
  isOutputActive: boolean;
  modeClass: string;
  nodeId: string;
  side: ConnectorSide;
};

type WorkflowEditorAuxiliaryPort = {
  actionIcon: string;
  ariaLabel: string;
  id: AgentAuxiliaryPortId;
  isActive: boolean;
  isCandidate: boolean;
  isConnected: boolean;
  isWarning: boolean;
  label: string;
  modelProviderAppId?: string;
  nodeId: string;
  stateLabel: string;
  title: string;
};

export function renderWorkflowEditorNodeMarkup(params: {
  agentDisplayTitle: string;
  agentNeedsModel: boolean;
  auxiliaryPorts: WorkflowEditorAuxiliaryPort[];
  connectors: WorkflowEditorNodeConnector[];
  icon: string;
  isConnectionCandidate: boolean;
  isConnectionSource: boolean;
  isConnectionTarget: boolean;
  isExecutionFailed: boolean;
  isExecutionPending: boolean;
  isExecutionSucceeded: boolean;
  isSelected: boolean;
  node: WorkflowNode;
  showAgentKindLabel: boolean;
  title: string;
}): string {
  const connectorsMarkup = params.connectors
    .map((connector) => `
      <span
        class="workflow-editor-node-connector workflow-editor-node-connector--${connector.side}${connector.modeClass}${connector.isCandidate ? ' is-candidate' : ''}${connector.isOutputActive ? ' is-output-active' : ''}${connector.isInputActive ? ' is-input-active' : ''}"
        data-workflow-node-connector="${escapeHtml(connector.nodeId)}"
        data-workflow-node-connector-side="${connector.side}"
        aria-hidden="true"
      ></span>
    `)
    .join('');

  const executionIndicatorMarkup = params.isExecutionPending
    ? `
      <span
        class="workflow-editor-node-execution-indicator is-running"
        aria-label="Node running"
        title="Node running"
      >
        <i class="mdi mdi-loading mdi-spin"></i>
      </span>
    `
    : params.isExecutionSucceeded
      ? `
        <span
          class="workflow-editor-node-execution-indicator is-succeeded"
          aria-label="Node succeeded"
          title="Node succeeded"
        >
          <i class="mdi mdi-check"></i>
        </span>
      `
      : params.isExecutionFailed
        ? `
          <span
            class="workflow-editor-node-execution-indicator is-failed"
            aria-label="Node failed"
            title="Node failed"
          >
            <i class="mdi mdi-close"></i>
          </span>
        `
        : '';

  const auxiliaryPortsMarkup = params.node.kind === 'agent'
    ? `
      <span class="workflow-editor-node-auxiliary">
        ${params.auxiliaryPorts.map((port) => `
          <button
            type="button"
            class="workflow-editor-node-auxiliary-port${port.isCandidate ? ' is-candidate' : ''}${port.isActive ? ' is-active' : ''}${port.isConnected ? ' is-connected' : ''}${port.isWarning ? ' is-warning' : ''}"
            data-workflow-node-aux-node="${escapeHtml(port.nodeId)}"
            data-workflow-node-aux-port="${port.id}"
            ${port.modelProviderAppId ? `data-model-provider="${escapeHtml(port.modelProviderAppId)}"` : ''}
            title="${escapeHtml(port.title)}"
            aria-label="${escapeHtml(port.ariaLabel)}"
          >
            <span class="workflow-editor-node-auxiliary-handle" aria-hidden="true"></span>
            <span class="workflow-editor-node-auxiliary-label">
              <span class="workflow-editor-node-auxiliary-text">${escapeHtml(port.label)}</span>
              <span class="workflow-editor-node-auxiliary-state">${escapeHtml(port.stateLabel)}</span>
            </span>
            <span class="workflow-editor-node-auxiliary-action" aria-hidden="true">
              <i class="mdi ${port.actionIcon}"></i>
            </span>
          </button>
        `).join('')}
      </span>
    `
    : '';

  const cardMarkup = params.node.kind === 'agent'
    ? `
      <span class="workflow-editor-node-card">
        <span class="workflow-editor-agent-panel">
          <span class="workflow-editor-agent-head">
            <span class="workflow-editor-agent-brand">
              <span class="workflow-editor-agent-icon">
                <i class="mdi ${escapeHtml(params.icon)}"></i>
              </span>
            </span>
            <span class="workflow-editor-agent-copy">
              <span class="workflow-editor-agent-title">${escapeHtml(params.agentDisplayTitle)}</span>
              ${params.showAgentKindLabel ? '<span class="workflow-editor-agent-kind">AI agent</span>' : ''}
            </span>
          </span>
          <span class="workflow-editor-agent-divider" aria-hidden="true"></span>
          ${auxiliaryPortsMarkup}
        </span>
      </span>
    `
    : `
      <span class="workflow-editor-node-card">
        <span class="workflow-editor-node-icon">
          <i class="mdi ${escapeHtml(params.icon)}"></i>
        </span>
      </span>
    `;

  const copyMarkup = params.node.kind === 'agent'
    ? ''
    : `
      <span class="workflow-editor-node-copy">
        <span class="workflow-editor-node-title">${escapeHtml(params.title)}</span>
      </span>
    `;

  const nodeToolbarMarkup = params.isSelected
    ? `
      <div class="workflow-node-toolbar" data-node-toolbar="${escapeHtml(params.node.id)}">
        <button
          type="button"
          class="workflow-node-toolbar-button"
          data-node-action="run"
          data-node-action-id="${escapeHtml(params.node.id)}"
          aria-label="Run node"
          ${params.isExecutionPending ? 'disabled' : ''}
        >
          <i class="mdi ${params.isExecutionPending ? 'mdi-loading mdi-spin' : 'mdi-play'}"></i>
        </button>
        <button
          type="button"
          class="workflow-node-toolbar-button"
          data-node-action="settings"
          data-node-action-id="${escapeHtml(params.node.id)}"
          aria-label="Open node settings"
        >
          <i class="mdi mdi-tune-variant"></i>
        </button>
        <button
          type="button"
          class="workflow-node-toolbar-button"
          data-node-action="delete"
          data-node-action-id="${escapeHtml(params.node.id)}"
          aria-label="Delete node"
        >
          <i class="mdi mdi-trash-can-outline"></i>
        </button>
      </div>
    `
    : '';

  return `
    <article
      class="workflow-editor-node workflow-editor-node--${escapeHtml(params.node.kind)}${params.isSelected ? ' is-selected' : ''}${params.isConnectionSource ? ' is-connection-source' : ''}${params.isConnectionCandidate ? ' is-connection-candidate' : ''}${params.isConnectionTarget ? ' is-connection-target' : ''}${params.agentNeedsModel ? ' is-agent-incomplete' : ''}${params.isExecutionPending ? ' is-executing' : ''}${params.isExecutionSucceeded ? ' is-execution-succeeded' : ''}${params.isExecutionFailed ? ' is-execution-failed' : ''}"
      data-workflow-node-id="${escapeHtml(params.node.id)}"
      tabindex="0"
    >
      ${nodeToolbarMarkup}
      ${connectorsMarkup}
      ${executionIndicatorMarkup}
      ${cardMarkup}
      ${copyMarkup}
    </article>
  `;
}

function renderPaletteDefinitionCards(definitions: WorkflowNodeDefinition[]): string {
  return definitions
    .map(
      (definition) => `
        <button type="button" class="workflow-template-card" data-add-node="${escapeHtml(definition.type)}">
          <span class="workflow-template-icon">
            <i class="mdi ${escapeHtml(definition.icon ?? 'mdi-vector-square')}"></i>
          </span>
          <span class="workflow-template-copy">
            <span class="workflow-template-title">${escapeHtml(definition.label)}</span>
            <span class="workflow-template-description">${escapeHtml(definition.description)}</span>
          </span>
        </button>
      `,
    )
    .join('');
}

export function renderNodePaletteMarkup(sections: WorkflowPaletteSection[]): string {
  return sections
    .map(
      (section) => `
        <div class="workflow-block-group">
          <div class="workflow-block-group-heading">
            <div class="workflow-block-group-title">
              ${
                section.icon
                  ? `<i class="mdi ${escapeHtml(section.icon)}"></i>`
                  : ''
              }
              <span>${escapeHtml(section.label)}</span>
            </div>
            <div class="workflow-block-group-copy">${escapeHtml(section.description)}</div>
          </div>
          ${
            section.definitions.length > 0
              ? `<div class="workflow-block-grid">${renderPaletteDefinitionCards(section.definitions)}</div>`
              : ''
          }
        </div>
      `,
    )
    .join('');
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
