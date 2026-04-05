import { escapeHtml } from '../../utils';

export function renderSettingsSection(params: {
  body: string;
  description: string;
  title: string;
}): string {
  if (!params.body.trim()) {
    return '';
  }

  const hasSectionHead = params.title.trim().length > 0 || params.description.trim().length > 0;

  return `
    <section class="workflow-editor-settings-section">
      ${hasSectionHead
        ? `
          <div class="workflow-editor-settings-section-head">
            ${params.title.trim()
              ? `<div class="workflow-editor-settings-section-title">${escapeHtml(params.title)}</div>`
              : ''}
            ${params.description.trim()
              ? `<div class="workflow-editor-settings-section-description">${escapeHtml(params.description)}</div>`
              : ''}
          </div>
        `
        : ''}
      <div class="workflow-editor-settings-section-body">
        ${params.body}
      </div>
    </section>
  `;
}
