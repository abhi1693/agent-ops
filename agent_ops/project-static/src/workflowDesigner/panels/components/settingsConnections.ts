import type {
  WorkflowConnection,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowSettingsPresentation,
} from '../../types';
import { escapeHtml, getConfigString } from '../../utils';
import { renderSettingsSection } from './settingsSection';
import { renderRequiredBadge } from './settingsShared';

function isConnectionSlotVisible(
  node: WorkflowNode,
  slot: NonNullable<WorkflowNodeDefinition['connection_slots']>[number],
): boolean {
  if (!slot.visible_when) {
    return true;
  }

  return Object.entries(slot.visible_when).every(([configKey, allowedValues]) => {
    const currentValue = getConfigString(node.config, configKey);
    return allowedValues.includes(currentValue);
  });
}

export function renderNodeConnectionSection(params: {
  connectionCreateUrl?: string | null;
  connections: WorkflowConnection[];
  node: WorkflowNode;
  nodeDefinition: WorkflowNodeDefinition;
  presentation: WorkflowSettingsPresentation;
}): string {
  const connectionSlots = params.nodeDefinition.connection_slots ?? [];
  const visibleConnectionSlots = connectionSlots.filter((slot) => isConnectionSlotVisible(params.node, slot));
  if (visibleConnectionSlots.length === 0) {
    return '';
  }

  const connectionPresentation = params.presentation.groups.connection;
  const body = visibleConnectionSlots
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
      const selectPlaceholder = selectableConnections.length === 0 ? 'No credentials yet' : 'Select credential';

      let setupCredentialButton = '';
      const actionButtons: string[] = [];
      if (params.connectionCreateUrl) {
        setupCredentialButton = `
          <button
            type="button"
            class="btn btn-sm btn-outline-secondary"
            data-workflow-connection-create="${escapeHtml(params.connectionCreateUrl)}"
            data-workflow-connection-default-type="${escapeHtml(slot.allowed_connection_types[0] ?? '')}"
          >
            Set up credential
          </button>
        `;
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
          <div class="workflow-editor-settings-credential-row">
            <select
              id="${escapeHtml(fieldId)}"
              class="form-select workflow-editor-settings-control"
              data-node-setting-key="${escapeHtml(slot.key)}"
              data-node-setting-type="select"
            >
              <option value="">${escapeHtml(selectPlaceholder)}</option>
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
            ${setupCredentialButton}
          </div>
          ${actionButtons.length > 0 ? `<div class="workflow-editor-settings-action-row">${actionButtons.join('')}</div>` : ''}
        </div>
      `;
    })
    .join('');

  return renderSettingsSection({
    body,
    description: visibleConnectionSlots.length > 1 ? connectionPresentation?.description ?? '' : '',
    title: visibleConnectionSlots.length > 1 ? connectionPresentation?.title ?? 'Credentials' : '',
  });
}
