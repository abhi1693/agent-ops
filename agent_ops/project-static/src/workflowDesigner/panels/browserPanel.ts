import type {
  WorkflowNodeCatalogSection,
  WorkflowNodeDefinition,
  WorkflowPaletteSection,
} from '../types';
import { escapeHtml } from '../utils';

type BrowserRenderHelpers = {
  formatKindLabel: (kind: string) => string;
  getCatalogSectionLabel: (catalogSection: WorkflowNodeCatalogSection | string | null | undefined) => string | null;
  getProviderMonogram: (label: string, appId?: string) => string;
  isModelProvider: (definition: WorkflowNodeDefinition) => boolean;
};

function getRealAppId(definition: WorkflowNodeDefinition): string {
  const appId = definition.app_id?.trim();
  if (!appId || appId === 'builtins') {
    return '';
  }

  return appId;
}

export function renderPaletteDefinitions(
  definitions: WorkflowNodeDefinition[],
  helpers: BrowserRenderHelpers,
): string {
  return definitions
    .map((definition) => {
      const icon = definition.icon ?? 'mdi-vector-square';
      const appId = getRealAppId(definition);
      const isModelProvider = helpers.isModelProvider(definition);
      const sectionLabel = helpers.getCatalogSectionLabel(definition.catalog_section);
      const meta = isModelProvider
        ? 'Model provider'
        : sectionLabel || helpers.formatKindLabel(definition.kind) || definition.kind;
      const description = isModelProvider
        ? definition.app_description || definition.description
        : definition.description;
      const iconMarkup = isModelProvider
        ? `<span class="workflow-node-browser-item-monogram">${escapeHtml(
            helpers.getProviderMonogram(definition.label, appId),
          )}</span>`
        : `<i class="mdi ${escapeHtml(icon)}"></i>`;

      return `
        <button
          type="button"
          class="workflow-node-browser-item"
          data-node-browser-item="${escapeHtml(definition.type)}"
          data-app-id="${escapeHtml(appId)}"
          data-model-provider="${isModelProvider ? 'true' : 'false'}"
          aria-label="${escapeHtml(definition.label)}"
        >
          <span class="workflow-node-browser-item-icon${isModelProvider ? ' is-model-provider' : ''}">
            ${iconMarkup}
          </span>
          <span class="workflow-node-browser-item-copy">
            <span class="workflow-node-browser-item-title">${escapeHtml(definition.label)}</span>
            <span class="workflow-node-browser-item-description">${escapeHtml(description)}</span>
            <span class="workflow-node-browser-item-meta">${escapeHtml(meta)}</span>
          </span>
        </button>
      `;
    })
    .join('');
}

export function renderPaletteSections(
  sections: WorkflowPaletteSection[],
  renderDefinitions: (definitions: WorkflowNodeDefinition[]) => string,
): string {
  return sections
    .map((section) => `
      <section class="workflow-node-browser-section" data-app-id="${escapeHtml(section.id)}">
        <div class="workflow-node-browser-section-head">
          <span class="workflow-node-browser-section-badge" aria-hidden="true">
            ${
              section.icon
                ? `<i class="mdi ${escapeHtml(section.icon)}"></i>`
                : escapeHtml(section.label.slice(0, 2).toUpperCase())
            }
          </span>
          <span class="workflow-node-browser-section-copy">
            <span class="workflow-node-browser-section-title">${escapeHtml(section.label)}</span>
            ${
              section.description
                ? `<span class="workflow-node-browser-section-description">${escapeHtml(section.description)}</span>`
                : ''
            }
          </span>
        </div>
        ${
          section.definitions.length > 0
            ? `<div class="workflow-node-browser-grid">${renderDefinitions(section.definitions)}</div>`
            : ''
        }
      </section>
    `)
    .join('');
}
