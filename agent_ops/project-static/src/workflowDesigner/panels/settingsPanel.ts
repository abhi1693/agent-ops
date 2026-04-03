import { escapeHtml } from '../utils';

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
