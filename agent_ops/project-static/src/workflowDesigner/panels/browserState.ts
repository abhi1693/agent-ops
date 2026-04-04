import type {
  AgentAuxiliaryPortId,
  WorkflowCatalogGroup,
  WorkflowNodeSelectionPresentation,
  WorkflowCatalogSection,
  WorkflowNodeDefinition,
  WorkflowPaletteSection,
} from '../types';
import { escapeHtml, formatKindLabel } from '../utils';
import { isModelDefinition } from '../registry/modelDefinitions';
import { renderPaletteDefinitions, renderPaletteSections } from './browserPanel';

export type BrowserView =
  | {
      kind: 'next-step-root';
    }
  | {
      backTo?: 'next-step-root';
      kind: 'trigger-root';
    }
  | {
      backTo: 'next-step-root' | 'trigger-root';
      kind: 'trigger-apps';
    }
  | {
      appId: string;
      backTo: 'app-actions' | 'trigger-apps';
      kind: 'app-details';
    }
  | {
      category: string;
      kind: 'category-details';
    }
  | {
      kind: 'app-actions';
    };

type BrowserListItemParams = {
  action: 'navigate' | 'select';
  actionValue: string;
  appId?: string;
  description: string;
  icon?: string | null;
  isModelProvider?: boolean;
  label: string;
  meta?: string;
};

type BrowserRenderHelpers = {
  definitions: WorkflowNodeDefinition[];
  filteredSections: WorkflowPaletteSection[];
};

export type BrowserRenderParams = BrowserRenderHelpers & {
  allowedNodeTypes: string[] | null;
  browserView: BrowserView;
  groups: WorkflowCatalogGroup[];
  catalogSections: WorkflowCatalogSection[];
  insertPort: AgentAuxiliaryPortId | undefined;
  isEmptyWorkflow: boolean;
  presentation: WorkflowNodeSelectionPresentation;
  searchQuery: string;
};

export type BrowserRenderResult = {
  description: string;
  emptyMessage: string;
  hideSearch: boolean;
  markup: string;
  searchPlaceholder: string;
  showBackButton: boolean;
  title: string;
};

export function getDefaultBrowserView(isEmptyWorkflow: boolean): BrowserView {
  return isEmptyWorkflow ? { kind: 'trigger-root' } : { kind: 'next-step-root' };
}

export function getPreviousBrowserView(
  browserView: BrowserView,
  isEmptyWorkflow: boolean,
): BrowserView | null {
  if (browserView.kind === 'app-details') {
    return browserView.backTo === 'trigger-apps'
      ? { backTo: isEmptyWorkflow ? 'trigger-root' : 'next-step-root', kind: 'trigger-apps' }
      : { kind: 'app-actions' };
  }

  if (browserView.kind === 'trigger-apps') {
    return browserView.backTo === 'next-step-root'
      ? { backTo: 'next-step-root', kind: 'trigger-root' }
      : { kind: 'trigger-root' };
  }

  if (browserView.kind === 'category-details' || browserView.kind === 'app-actions') {
    return { kind: 'next-step-root' };
  }

  if (browserView.kind === 'trigger-root' && browserView.backTo === 'next-step-root') {
    return { kind: 'next-step-root' };
  }

  return null;
}

export function getCatalogSectionLabel(
  catalogSections: WorkflowCatalogSection[],
  catalogSection: string | null | undefined,
): string | null {
  return catalogSections.find((section) => section.id === catalogSection)?.label ?? null;
}

function getCatalogGroup(
  groups: WorkflowCatalogGroup[],
  categoryId: string,
): WorkflowCatalogGroup | undefined {
  return groups.find((category) => category.id === categoryId);
}

function filterNodeDefinitions(
  definitions: WorkflowNodeDefinition[],
  query: string,
): WorkflowNodeDefinition[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return definitions;
  }

  return definitions.filter((definition) => {
    const fieldTerms = definition.fields.reduce<string[]>((terms, field) => {
      terms.push(field.key, field.label);
      (field.options ?? []).forEach((option) => {
        terms.push(option.label, option.value);
      });
      return terms;
    }, []);
    const haystack = [
      definition.label,
      definition.description,
      definition.type,
      definition.kind,
      definition.catalog_section ?? '',
      definition.app_label ?? '',
      definition.app_description ?? '',
      typeof definition.config?.model === 'string' ? definition.config.model : '',
      ...fieldTerms,
    ]
      .join(' ')
      .toLowerCase();

    return haystack.includes(normalizedQuery);
  });
}

function getRealAppId(definition: WorkflowNodeDefinition | undefined): string {
  const appId = definition?.app_id?.trim();
  if (!appId || appId === 'builtins') {
    return '';
  }

  return appId;
}

function renderBrowserIcon(params: {
  icon?: string | null;
  isModelProvider?: boolean;
}): string {
  if (params.isModelProvider) {
    return '<i class="mdi mdi-robot-outline"></i>';
  }

  if (params.icon && params.icon.trim().length > 0) {
    return `<i class="mdi ${escapeHtml(params.icon)}"></i>`;
  }

  return '<i class="mdi mdi-vector-square"></i>';
}

function renderBrowserListItem(params: BrowserListItemParams): string {
  const actionAttributes = params.action === 'select'
    ? `data-node-browser-item="${escapeHtml(params.actionValue)}"`
    : `data-node-browser-nav="${escapeHtml(params.actionValue)}"`;
  const trailingMarkup = params.action === 'navigate'
    ? `
        <span class="workflow-node-browser-item-chevron" aria-hidden="true">
          <i class="mdi mdi-chevron-right"></i>
        </span>
      `
    : '';

  return `
    <button
      type="button"
      class="workflow-node-browser-item${params.action === 'navigate' ? ' is-navigation' : ''}"
      ${actionAttributes}
      ${params.appId ? `data-app-id="${escapeHtml(params.appId)}"` : ''}
      aria-label="${escapeHtml(params.label)}"
    >
      <span class="workflow-node-browser-item-icon${params.isModelProvider ? ' is-model-provider' : ''}">
        ${renderBrowserIcon({
          icon: params.icon,
          isModelProvider: params.isModelProvider,
        })}
      </span>
      <span class="workflow-node-browser-item-copy">
        <span class="workflow-node-browser-item-title">${escapeHtml(params.label)}</span>
        <span class="workflow-node-browser-item-description">${escapeHtml(params.description)}</span>
        ${params.meta ? `<span class="workflow-node-browser-item-meta">${escapeHtml(params.meta)}</span>` : ''}
      </span>
      ${trailingMarkup}
    </button>
  `;
}

function renderBrowserDefinitionList(
  definitions: WorkflowNodeDefinition[],
  catalogSections: WorkflowCatalogSection[],
): string {
  return definitions
    .map((definition) =>
      renderBrowserListItem({
        action: 'select',
        actionValue: definition.type,
        appId: getRealAppId(definition),
        description: definition.description,
        icon: definition.icon,
        isModelProvider: isModelDefinition(definition),
        label: definition.label,
        meta: definition.catalog_section
          ? getCatalogSectionLabel(catalogSections, definition.catalog_section) ?? undefined
          : undefined,
      }))
    .join('');
}

function getAppNodeDefinitions(
  appId: string,
  definitions: WorkflowNodeDefinition[],
): WorkflowNodeDefinition[] {
  return definitions
    .filter((definition) => definition.app_id === appId && !isModelDefinition(definition))
    .sort((first, second) => {
      if (first.kind !== second.kind) {
        if (first.kind === 'trigger') {
          return -1;
        }
        if (second.kind === 'trigger') {
          return 1;
        }
      }

      return first.label.localeCompare(second.label);
    });
}

function getAppTriggerDefinitions(definitions: WorkflowNodeDefinition[]): WorkflowNodeDefinition[] {
  return definitions.filter(
    (definition) => definition.group === 'app_trigger',
  );
}

function getAppActionDefinitions(definitions: WorkflowNodeDefinition[]): WorkflowNodeDefinition[] {
  return definitions.filter(
    (definition) => definition.group === 'app_action' && !isModelDefinition(definition),
  );
}

function getNextStepCategoryDefinitions(
  categoryId: string,
  definitions: WorkflowNodeDefinition[],
): WorkflowNodeDefinition[] {
  return definitions
    .filter((definition) => definition.group === categoryId)
    .sort((first, second) => first.label.localeCompare(second.label));
}

function formatPresentationText(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => values[key] ?? match);
}

export function renderBrowserState(params: BrowserRenderParams): BrowserRenderResult {
  const availableDefinitions = params.allowedNodeTypes
    ? params.definitions.filter((definition) => params.allowedNodeTypes?.includes(definition.type))
    : params.definitions;
  const nodeSelection = params.presentation;
  const browserRenderHelpers = {
    formatKindLabel,
    getCatalogSectionLabel: (catalogSection: string | null | undefined) =>
      getCatalogSectionLabel(params.catalogSections, catalogSection),
    isModelProvider: isModelDefinition,
  };
  const renderDefinitions = (definitions: WorkflowNodeDefinition[]): string =>
    renderPaletteDefinitions(definitions, browserRenderHelpers);
  const renderSections = (sections: WorkflowPaletteSection[]): string =>
    renderPaletteSections(
      sections
        .map((section) => ({
          ...section,
          definitions: filterNodeDefinitions(section.definitions, params.searchQuery),
        }))
        .filter((section) => section.definitions.length > 0),
      renderDefinitions,
    );

  let title = nodeSelection.common.default_title;
  let description = params.insertPort
    ? nodeSelection.common.connect_description
    : nodeSelection.common.add_description;
  let emptyMessage = nodeSelection.common.default_empty;
  let markup = renderSections(params.filteredSections);
  let searchPlaceholder = nodeSelection.common.default_search_placeholder;
  let hideSearch = false;

  if (params.browserView.kind === 'trigger-root') {
    const triggerDefinitions = availableDefinitions.filter((definition) => definition.kind === 'trigger');
    const manualTrigger = triggerDefinitions.find((definition) => definition.type === 'core.manual_trigger');
    const scheduleTrigger = triggerDefinitions.find((definition) => definition.type === 'core.schedule_trigger');
    const appTriggerDefinitions = getAppTriggerDefinitions(availableDefinitions);
    const rootItems = [
      ...(manualTrigger ? [renderBrowserListItem({
        action: 'select',
        actionValue: manualTrigger.type,
        appId: getRealAppId(manualTrigger),
        description: manualTrigger.description,
        icon: 'mdi-cursor-default-click-outline',
        label: nodeSelection.trigger_root.items.manual.label,
      })] : []),
      ...(appTriggerDefinitions.length > 0 ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'trigger-apps',
        description: nodeSelection.trigger_root.items.app_event.description,
        icon: 'mdi-connection',
        label: nodeSelection.trigger_apps.title,
      })] : []),
      ...(scheduleTrigger ? [renderBrowserListItem({
        action: 'select',
        actionValue: scheduleTrigger.type,
        appId: getRealAppId(scheduleTrigger),
        description: scheduleTrigger.description,
        icon: 'mdi-clock-outline',
        label: nodeSelection.trigger_root.items.schedule.label,
      })] : []),
      ...triggerDefinitions
        .filter((definition) =>
          definition.type !== manualTrigger?.type
          && definition.type !== scheduleTrigger?.type
          && !appTriggerDefinitions.some((appDefinition) => appDefinition.type === definition.type))
        .map((definition) =>
          renderBrowserListItem({
            action: 'select',
            actionValue: definition.type,
            appId: getRealAppId(definition),
            description: definition.description,
            icon: definition.icon,
            label: definition.label,
          })),
    ];
    const normalizedQuery = params.searchQuery.trim().toLowerCase();
    const filteredItems = normalizedQuery.length === 0
      ? rootItems
      : rootItems.filter((itemMarkup) => itemMarkup.toLowerCase().includes(normalizedQuery));

    title = params.browserView.backTo === 'next-step-root'
      ? nodeSelection.trigger_root.additional.label
      : nodeSelection.trigger_root.initial.title;
    description = params.browserView.backTo === 'next-step-root'
      ? nodeSelection.trigger_root.additional.description
      : nodeSelection.trigger_root.initial.description;
    emptyMessage = nodeSelection.trigger_root.empty;
    searchPlaceholder = nodeSelection.trigger_root.search_placeholder;
    markup = filteredItems.join('');
  } else if (params.browserView.kind === 'trigger-apps') {
    const appItems = Array.from(
      getAppTriggerDefinitions(availableDefinitions).reduce<Map<string, WorkflowNodeDefinition>>((items, definition) => {
        const appId = getRealAppId(definition);
        if (!appId || items.has(appId)) {
          return items;
        }

        items.set(appId, definition);
        return items;
      }, new Map()),
    )
      .map(([appId, definition]) => ({
        appId,
        definition,
      }))
      .filter(({ definition }) => {
        const normalizedQuery = params.searchQuery.trim().toLowerCase();
        if (!normalizedQuery) {
          return true;
        }

        return [
          definition.app_label ?? '',
          definition.app_description ?? '',
          definition.label,
        ]
          .join(' ')
          .toLowerCase()
          .includes(normalizedQuery);
      })
      .sort((first, second) =>
        (first.definition.app_label ?? first.definition.label).localeCompare(
          second.definition.app_label ?? second.definition.label,
        ));

    title = nodeSelection.trigger_apps.title;
    description = '';
    emptyMessage = nodeSelection.trigger_apps.empty;
    searchPlaceholder = nodeSelection.trigger_apps.search_placeholder;
    markup = appItems
      .map(({ appId, definition }) =>
        renderBrowserListItem({
          action: 'navigate',
          actionValue: 'app-details',
          appId,
          description: definition.app_description || definition.description,
          icon: definition.app_icon || definition.icon,
          label: definition.app_label || definition.label,
          meta: nodeSelection.trigger_apps.trigger_meta,
        }))
      .join('');
  } else if (params.browserView.kind === 'app-details') {
    const appDefinitions = getAppNodeDefinitions(params.browserView.appId, availableDefinitions);
    const triggerDefinitions = appDefinitions.filter((definition) => definition.kind === 'trigger');
    const actionDefinitions = appDefinitions.filter((definition) => definition.kind !== 'trigger');
    const appDefinition = appDefinitions[0];
    const detailSections = params.browserView.backTo === 'trigger-apps'
      ? [{
        count: triggerDefinitions.length,
        definitions: triggerDefinitions,
        title: nodeSelection.app_details.sections.triggers,
      }]
      : [{
        count: actionDefinitions.length,
        definitions: actionDefinitions,
        title: nodeSelection.app_details.sections.actions,
      }];

    title = appDefinition?.app_label || appDefinition?.label || nodeSelection.app_details.default_title;
    description = appDefinition?.app_description || '';
    emptyMessage = nodeSelection.app_details.empty;
    hideSearch = true;
    markup = appDefinitions.length > 0
      ? `
          <div class="workflow-node-browser-details">
            ${detailSections
              .filter((section) => section.count > 0)
              .map((section) => `
                <section class="workflow-node-browser-detail-section">
                  <div class="workflow-node-browser-detail-title">${section.title} (${section.count})</div>
                  <div class="workflow-node-browser-grid">${renderBrowserDefinitionList(section.definitions, params.catalogSections)}</div>
                </section>
              `)
              .join('')}
          </div>
        `
      : '';
  } else if (params.insertPort) {
    const insertPresentation = params.insertPort === 'ai_languageModel'
      ? nodeSelection.insert.model_provider
      : nodeSelection.insert.tool;

    title = insertPresentation.title;
    description = insertPresentation.description;
    emptyMessage = insertPresentation.empty;
    searchPlaceholder = insertPresentation.search_placeholder;
    if (params.insertPort === 'ai_languageModel') {
      const modelDefinitions = filterNodeDefinitions(
        availableDefinitions.filter((definition) => isModelDefinition(definition)),
        params.searchQuery,
      );
      markup = modelDefinitions.length > 0
        ? `<div class="workflow-node-browser-list workflow-node-browser-list--providers">${renderDefinitions(modelDefinitions)}</div>`
        : '';
    }
  } else if (params.browserView.kind === 'next-step-root') {
    const actionDefinitions = getAppActionDefinitions(availableDefinitions);
    const categoryItems = params.groups
      .filter((category) => getNextStepCategoryDefinitions(category.id, availableDefinitions).length > 0)
      .map((category) =>
        renderBrowserListItem({
          action: 'navigate',
          actionValue: `next-category:${category.id}`,
          description: category.description,
          icon: category.icon,
          label: category.label,
        }));
    const rootItems = [
      ...categoryItems,
      ...(actionDefinitions.length > 0 ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'app-actions',
        description: nodeSelection.next_step_root.items.app_action.description,
        icon: 'mdi-earth',
        label: nodeSelection.next_step_root.items.app_action.label,
      })] : []),
      ...(availableDefinitions.some((definition) => definition.kind === 'trigger') ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'trigger-root',
        description: nodeSelection.trigger_root.additional.description,
        icon: 'mdi-lightning-bolt-outline',
        label: nodeSelection.trigger_root.additional.label,
      })] : []),
    ];
    const normalizedQuery = params.searchQuery.trim().toLowerCase();
    const filteredItems = normalizedQuery.length === 0
      ? rootItems
      : rootItems.filter((itemMarkup) => itemMarkup.toLowerCase().includes(normalizedQuery));

    title = nodeSelection.next_step_root.title;
    description = '';
    emptyMessage = nodeSelection.next_step_root.empty;
    searchPlaceholder = nodeSelection.next_step_root.search_placeholder;
    markup = filteredItems.join('');
  } else if (params.browserView.kind === 'app-actions') {
    const appItems = Array.from(
      getAppActionDefinitions(availableDefinitions).reduce<Map<string, WorkflowNodeDefinition>>((items, definition) => {
        const appId = getRealAppId(definition);
        if (!appId || items.has(appId)) {
          return items;
        }

        items.set(appId, definition);
        return items;
      }, new Map()),
    )
      .map(([appId, definition]) => ({
        appId,
        definition,
      }))
      .filter(({ definition }) => {
        const normalizedQuery = params.searchQuery.trim().toLowerCase();
        if (!normalizedQuery) {
          return true;
        }

        return [
          definition.app_label ?? '',
          definition.app_description ?? '',
          definition.label,
        ]
          .join(' ')
          .toLowerCase()
          .includes(normalizedQuery);
      })
      .sort((first, second) =>
        (first.definition.app_label ?? first.definition.label).localeCompare(
          second.definition.app_label ?? second.definition.label,
        ));

    title = nodeSelection.app_actions.title;
    description = '';
    emptyMessage = nodeSelection.app_actions.empty;
    searchPlaceholder = nodeSelection.app_actions.search_placeholder;
    markup = appItems
      .map(({ appId, definition }) =>
        renderBrowserListItem({
          action: 'navigate',
          actionValue: 'app-details',
          appId,
          description: definition.app_description || definition.description,
          icon: definition.app_icon || definition.icon,
          label: definition.app_label || definition.label,
          meta: nodeSelection.app_actions.action_meta,
        }))
      .join('');
  } else if (params.browserView.kind === 'category-details') {
    const categoryMeta = getCatalogGroup(params.groups, params.browserView.category);
    const categoryDefinitions = filterNodeDefinitions(
      getNextStepCategoryDefinitions(params.browserView.category, availableDefinitions),
      params.searchQuery,
    );

    title = categoryMeta?.label ?? params.browserView.category;
    description = categoryMeta?.description ?? '';
    emptyMessage = categoryMeta
      ? formatPresentationText(nodeSelection.category_details.empty_template, {
        group: categoryMeta.label.toLowerCase(),
      })
      : nodeSelection.category_details.fallback_empty;
    searchPlaceholder = nodeSelection.category_details.search_placeholder;
    markup = categoryDefinitions.length > 0
      ? `<div class="workflow-node-browser-list">${renderBrowserDefinitionList(categoryDefinitions, params.catalogSections)}</div>`
      : '';
  }

  return {
    description,
    emptyMessage,
    hideSearch,
    markup,
    searchPlaceholder,
    showBackButton:
      (params.browserView.kind === 'trigger-root' && params.browserView.backTo === 'next-step-root')
      || params.browserView.kind === 'trigger-apps'
      || params.browserView.kind === 'app-details'
      || params.browserView.kind === 'app-actions'
      || params.browserView.kind === 'category-details',
    title,
  };
}
