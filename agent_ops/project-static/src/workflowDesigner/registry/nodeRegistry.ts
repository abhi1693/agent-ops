import { getNodeCategoryForKind } from './categories';
import type {
  WorkflowNodeCatalogSection,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeTemplate,
  WorkflowPaletteSection,
} from '../types';

export type WorkflowNodeRegistry = {
  definitions: WorkflowNodeDefinition[];
  definitionMap: Map<string, WorkflowNodeDefinition>;
  paletteSections: WorkflowPaletteSection[];
};

const CHAT_MODEL_NODE_TYPES = new Set<string>([
  'tool.deepseek_chat_model',
  'tool.fireworks_chat_model',
  'tool.groq_chat_model',
  'tool.mistral_chat_model',
  'tool.openai_chat_model',
  'tool.openrouter_chat_model',
  'tool.xai_chat_model',
]);
const WORKFLOW_CATALOG_SECTION_ORDER: WorkflowNodeCatalogSection[] = [
  'triggers',
  'flow',
  'data',
  'apps',
];
const WORKFLOW_CATALOG_SECTION_META: Record<
  WorkflowNodeCatalogSection,
  {
    description: string;
    icon: string;
    label: string;
  }
> = {
  triggers: {
    label: 'Triggers',
    description: 'Choose how the workflow starts.',
    icon: 'mdi-rocket-launch-outline',
  },
  flow: {
    label: 'Flow',
    description: 'Control execution and AI-driven workflow steps.',
    icon: 'mdi-vector-polyline',
  },
  data: {
    label: 'Data',
    description: 'Set values, render templates, and resolve workflow data.',
    icon: 'mdi-database-outline',
  },
  apps: {
    label: 'Apps',
    description: 'Connect workflow steps to external systems and providers.',
    icon: 'mdi-apps',
  },
};

function createNodeDefinition(template: WorkflowNodeTemplate): WorkflowNodeDefinition {
  return {
    app_description: template.app_description,
    app_icon: template.app_icon,
    app_id: template.app_id,
    app_label: template.app_label,
    catalog_section: template.catalog_section,
    category: getNodeCategoryForKind(template.kind),
    config: template.config,
    description: template.description,
    fields: template.fields,
    icon: template.icon,
    kind: template.kind,
    label: template.label,
    type: template.type,
    typeVersion: template.typeVersion ?? 1,
  };
}

function isChatModelDefinition(definition: WorkflowNodeDefinition): boolean {
  return CHAT_MODEL_NODE_TYPES.has(definition.type);
}

function normalizeCatalogSection(definition: WorkflowNodeDefinition): WorkflowNodeCatalogSection {
  if (definition.catalog_section && definition.catalog_section in WORKFLOW_CATALOG_SECTION_META) {
    return definition.catalog_section;
  }

  if (definition.kind === 'trigger') {
    return 'triggers';
  }

  if (definition.type === 'n8n-nodes-base.set' || definition.type === 'tool.template' || definition.type === 'tool.secret') {
    return 'data';
  }

  if (definition.kind === 'agent' || definition.kind === 'condition' || definition.kind === 'response') {
    return 'flow';
  }

  return 'apps';
}

export function buildNodeRegistry(nodeTemplates: WorkflowNodeTemplate[]): WorkflowNodeRegistry {
  const definitions = nodeTemplates.map(createNodeDefinition);
  const definitionMap = new Map(definitions.map((definition) => [definition.type, definition]));
  const sectionsById = new Map<WorkflowNodeCatalogSection, WorkflowPaletteSection>(
    WORKFLOW_CATALOG_SECTION_ORDER.map((sectionId) => [
      sectionId,
      {
        definitions: [],
        description: WORKFLOW_CATALOG_SECTION_META[sectionId].description,
        icon: WORKFLOW_CATALOG_SECTION_META[sectionId].icon,
        id: sectionId,
        label: WORKFLOW_CATALOG_SECTION_META[sectionId].label,
      },
    ]),
  );
  definitions.forEach((definition) => {
    if (isChatModelDefinition(definition)) {
      return;
    }

    sectionsById.get(normalizeCatalogSection(definition))?.definitions.push(definition);
  });
  const paletteSections = WORKFLOW_CATALOG_SECTION_ORDER
    .map((sectionId) => sectionsById.get(sectionId))
    .filter((section): section is WorkflowPaletteSection => Boolean(section && section.definitions.length));

  return {
    definitions,
    definitionMap,
    paletteSections,
  };
}

export function getNodeDefinition(
  registry: WorkflowNodeRegistry,
  node: WorkflowNode | undefined,
): WorkflowNodeDefinition | undefined {
  if (!node) {
    return undefined;
  }

  return registry.definitionMap.get(node.type);
}

export function getAvailablePaletteSections(
  registry: WorkflowNodeRegistry,
  definition: WorkflowDefinition,
): WorkflowPaletteSection[] {
  const hasTrigger = definition.nodes.some((node) => node.kind === 'trigger');

  return registry.paletteSections
    .map((section) => ({
      ...section,
      definitions: section.definitions.filter((definitionItem) => {
        if (definitionItem.kind === 'trigger') {
          return !hasTrigger;
        }

        return true;
      }),
    }))
    .filter((section) => section.definitions.length > 0);
}
