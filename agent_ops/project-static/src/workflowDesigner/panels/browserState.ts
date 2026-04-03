import type {
  AgentAuxiliaryPortId,
  WorkflowNodeCatalogSection,
  WorkflowNodeDefinition,
  WorkflowPaletteSection,
} from '../types';
import { escapeHtml, formatKindLabel } from '../utils';
import { isModelDefinition } from '../registry/modelDefinitions';
import { renderPaletteDefinitions, renderPaletteSections } from './browserPanel';

export type NextStepCategoryId = 'ai' | 'data' | 'flow' | 'core';

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
      category: NextStepCategoryId;
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
  insertPort: AgentAuxiliaryPortId | undefined;
  isEmptyWorkflow: boolean;
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

const NEXT_STEP_CATEGORY_META: Record<NextStepCategoryId, {
  description: string;
  icon: string;
  label: string;
}> = {
  ai: {
    description: 'Build autonomous agents, summarize or search documents, etc.',
    icon: 'mdi-robot-outline',
    label: 'AI',
  },
  data: {
    description: 'Manipulate, filter or convert data',
    icon: 'mdi-pencil-outline',
    label: 'Data transformation',
  },
  flow: {
    description: 'Branch, merge or control the flow.',
    icon: 'mdi-source-branch',
    label: 'Flow',
  },
  core: {
    description: 'Run built-in workflow steps.',
    icon: 'mdi-toolbox-outline',
    label: 'Core',
  },
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
  catalogSection: WorkflowNodeCatalogSection | string | null | undefined,
): string | null {
  switch (catalogSection) {
    case 'triggers':
      return 'Triggers';
    case 'flow':
      return 'Flow';
    case 'data':
      return 'Data';
    case 'apps':
      return 'Apps';
    default:
      return null;
  }
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

function renderBrowserDefinitionList(definitions: WorkflowNodeDefinition[]): string {
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
        meta: definition.catalog_section ? getCatalogSectionLabel(definition.catalog_section) ?? undefined : undefined,
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
    (definition) => definition.kind === 'trigger' && getRealAppId(definition) !== '' && getRealAppId(definition) !== 'core',
  );
}

function getAppActionDefinitions(definitions: WorkflowNodeDefinition[]): WorkflowNodeDefinition[] {
  return definitions.filter((definition) =>
    getRealAppId(definition) !== ''
    && getRealAppId(definition) !== 'core'
    && definition.kind !== 'trigger'
    && !isModelDefinition(definition));
}

function getNextStepCategoryDefinitions(
  category: NextStepCategoryId,
  definitions: WorkflowNodeDefinition[],
): WorkflowNodeDefinition[] {
  if (category === 'ai') {
    return definitions
      .filter((definition) => definition.kind === 'agent')
      .sort((first, second) => first.label.localeCompare(second.label));
  }

  if (category === 'data') {
    return definitions
      .filter((definition) => definition.catalog_section === 'data')
      .sort((first, second) => first.label.localeCompare(second.label));
  }

  if (category === 'flow') {
    return definitions
      .filter((definition) => definition.kind === 'condition')
      .sort((first, second) => first.label.localeCompare(second.label));
  }

  return definitions
    .filter((definition) => {
      const appId = getRealAppId(definition);
      return (appId === '' || appId === 'core')
        && definition.kind !== 'trigger'
        && definition.kind !== 'agent'
        && definition.kind !== 'condition'
        && !isModelDefinition(definition)
        && definition.catalog_section !== 'data';
    })
    .sort((first, second) => first.label.localeCompare(second.label));
}

export function renderBrowserState(params: BrowserRenderParams): BrowserRenderResult {
  const availableDefinitions = params.allowedNodeTypes
    ? params.definitions.filter((definition) => params.allowedNodeTypes?.includes(definition.type))
    : params.definitions;
  const browserRenderHelpers = {
    formatKindLabel,
    getCatalogSectionLabel,
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

  let title = 'Add node';
  let description = params.insertPort
    ? 'Choose the next step to connect from here.'
    : 'Choose the next step to add to this workflow.';
  let emptyMessage = 'No matching nodes';
  let markup = renderSections(params.filteredSections);
  let searchPlaceholder = 'Search nodes, apps, or actions';
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
        label: 'Trigger manually',
      })] : []),
      ...(appTriggerDefinitions.length > 0 ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'trigger-apps',
        description: 'Start the workflow from an event in one of your apps.',
        icon: 'mdi-connection',
        label: 'On app event',
      })] : []),
      ...(scheduleTrigger ? [renderBrowserListItem({
        action: 'select',
        actionValue: scheduleTrigger.type,
        appId: getRealAppId(scheduleTrigger),
        description: scheduleTrigger.description,
        icon: 'mdi-clock-outline',
        label: 'On a schedule',
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

    title = params.browserView.backTo === 'next-step-root' ? 'Add another trigger' : 'What triggers this workflow?';
    description = params.browserView.backTo === 'next-step-root'
      ? 'Triggers start your workflow. Workflows can have multiple triggers.'
      : 'A trigger is a step that starts your workflow';
    emptyMessage = 'No matching triggers';
    searchPlaceholder = 'Search nodes...';
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

    title = 'On app event';
    description = '';
    emptyMessage = 'No matching apps';
    searchPlaceholder = 'Search nodes...';
    markup = appItems
      .map(({ appId, definition }) =>
        renderBrowserListItem({
          action: 'navigate',
          actionValue: 'app-details',
          appId,
          description: definition.app_description || definition.description,
          icon: definition.app_icon || definition.icon,
          label: definition.app_label || definition.label,
          meta: 'Trigger nodes',
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
        title: 'Triggers',
      }]
      : [{
        count: actionDefinitions.length,
        definitions: actionDefinitions,
        title: 'Actions',
      }];

    title = appDefinition?.app_label || appDefinition?.label || 'Node details';
    description = appDefinition?.app_description || '';
    emptyMessage = 'No nodes available for this app';
    hideSearch = true;
    markup = appDefinitions.length > 0
      ? `
          <div class="workflow-node-browser-details">
            ${detailSections
              .filter((section) => section.count > 0)
              .map((section) => `
                <section class="workflow-node-browser-detail-section">
                  <div class="workflow-node-browser-detail-title">${section.title} (${section.count})</div>
                  <div class="workflow-node-browser-grid">${renderBrowserDefinitionList(section.definitions)}</div>
                </section>
              `)
              .join('')}
          </div>
        `
      : '';
  } else if (params.insertPort) {
    title = params.insertPort === 'ai_languageModel' ? 'Attach model provider' : 'Attach tool';
    description = params.insertPort === 'ai_languageModel'
      ? 'Choose a provider-backed model node. Each one includes curated presets and an optional custom override.'
      : 'Choose any tool or integration node to attach to this agent.';
    emptyMessage = params.insertPort === 'ai_languageModel'
      ? 'No matching model providers'
      : 'No matching tools';
    searchPlaceholder = params.insertPort === 'ai_languageModel' ? 'Search model providers' : 'Search tools';
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
    const rootItems = [
      ...(getNextStepCategoryDefinitions('ai', availableDefinitions).length > 0 ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'next-ai',
        description: NEXT_STEP_CATEGORY_META.ai.description,
        icon: NEXT_STEP_CATEGORY_META.ai.icon,
        label: NEXT_STEP_CATEGORY_META.ai.label,
      })] : []),
      ...(actionDefinitions.length > 0 ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'app-actions',
        description: 'Do something in an app or service like Elasticsearch or Prometheus.',
        icon: 'mdi-earth',
        label: 'Action in an app',
      })] : []),
      ...(getNextStepCategoryDefinitions('data', availableDefinitions).length > 0 ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'next-data',
        description: NEXT_STEP_CATEGORY_META.data.description,
        icon: NEXT_STEP_CATEGORY_META.data.icon,
        label: NEXT_STEP_CATEGORY_META.data.label,
      })] : []),
      ...(getNextStepCategoryDefinitions('flow', availableDefinitions).length > 0 ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'next-flow',
        description: NEXT_STEP_CATEGORY_META.flow.description,
        icon: NEXT_STEP_CATEGORY_META.flow.icon,
        label: NEXT_STEP_CATEGORY_META.flow.label,
      })] : []),
      ...(getNextStepCategoryDefinitions('core', availableDefinitions).length > 0 ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'next-core',
        description: NEXT_STEP_CATEGORY_META.core.description,
        icon: NEXT_STEP_CATEGORY_META.core.icon,
        label: NEXT_STEP_CATEGORY_META.core.label,
      })] : []),
      ...(availableDefinitions.some((definition) => definition.kind === 'trigger') ? [renderBrowserListItem({
        action: 'navigate',
        actionValue: 'trigger-root',
        description: 'Triggers start your workflow. Workflows can have multiple triggers.',
        icon: 'mdi-lightning-bolt-outline',
        label: 'Add another trigger',
      })] : []),
    ];
    const normalizedQuery = params.searchQuery.trim().toLowerCase();
    const filteredItems = normalizedQuery.length === 0
      ? rootItems
      : rootItems.filter((itemMarkup) => itemMarkup.toLowerCase().includes(normalizedQuery));

    title = 'What happens next?';
    description = '';
    emptyMessage = 'No matching node categories';
    searchPlaceholder = 'Search nodes...';
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

    title = 'Action in an app';
    description = '';
    emptyMessage = 'No matching apps';
    searchPlaceholder = 'Search nodes...';
    markup = appItems
      .map(({ appId, definition }) =>
        renderBrowserListItem({
          action: 'navigate',
          actionValue: 'app-details',
          appId,
          description: definition.app_description || definition.description,
          icon: definition.app_icon || definition.icon,
          label: definition.app_label || definition.label,
          meta: 'Action nodes',
        }))
      .join('');
  } else if (params.browserView.kind === 'category-details') {
    const categoryMeta = NEXT_STEP_CATEGORY_META[params.browserView.category];
    const categoryDefinitions = filterNodeDefinitions(
      getNextStepCategoryDefinitions(params.browserView.category, availableDefinitions),
      params.searchQuery,
    );

    title = categoryMeta.label;
    description = categoryMeta.description;
    emptyMessage = `No matching ${categoryMeta.label.toLowerCase()} nodes`;
    searchPlaceholder = 'Search nodes...';
    markup = categoryDefinitions.length > 0
      ? `<div class="workflow-node-browser-list">${renderBrowserDefinitionList(categoryDefinitions)}</div>`
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
