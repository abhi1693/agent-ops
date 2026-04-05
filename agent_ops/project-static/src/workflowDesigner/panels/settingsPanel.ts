import type { WorkflowSettingsPresentation } from '../types';
import { escapeHtml } from '../utils';
import { renderSettingsSection } from './components/settingsSection';

export { renderNodeConnectionSection } from './components/settingsConnections';
export { renderNodeSettingsFieldsMarkup } from './components/settingsFields';
export { renderSettingsSection } from './components/settingsSection';

export function renderSettingsOverviewSection(params: {
  presentation: WorkflowSettingsPresentation;
  nodeDefinitionLabel: string;
  nodeId: string;
}): string {
  const overviewPresentation = params.presentation.groups.overview;
  const overviewFields = overviewPresentation.fields ?? {};

  return renderSettingsSection({
    title: overviewPresentation.title,
    description: overviewPresentation.description,
    body: `
      <div class="workflow-editor-settings-group">
        <div class="workflow-editor-settings-help">${escapeHtml(overviewFields.type ?? 'Type')}</div>
        <div class="workflow-editor-settings-preview">${escapeHtml(params.nodeDefinitionLabel)}</div>
      </div>
      <div class="workflow-editor-settings-group">
        <div class="workflow-editor-settings-help">${escapeHtml(overviewFields.node_id ?? 'Node id')}</div>
        <div class="workflow-editor-settings-expression-hint"><code>${escapeHtml(params.nodeId)}</code></div>
      </div>
    `,
  });
}

export function renderSettingsIdentitySection(params: {
  nodeId: string;
  nodeLabel: string;
  presentation: WorkflowSettingsPresentation;
}): string {
  const identityPresentation = params.presentation.groups.identity;
  const identityFields = identityPresentation.fields ?? {};

  return renderSettingsSection({
    title: identityPresentation.title,
    description: identityPresentation.description,
    body: `
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
    `,
  });
}
