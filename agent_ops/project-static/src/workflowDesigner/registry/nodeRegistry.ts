import { getNodeCategoryForKind } from './categories';
import type {
  WorkflowConnection,
  WorkflowCatalogSection,
  WorkflowNodeCatalogSection,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowPaletteSection,
  WorkflowNodeTemplateField,
} from '../types';

export type WorkflowNodeRegistry = {
  definitions: WorkflowNodeDefinition[];
  definitionMap: Map<string, WorkflowNodeDefinition>;
  paletteSections: WorkflowPaletteSection[];
};

type WorkflowPaletteSectionAccumulator = WorkflowCatalogSection & {
  definitions: WorkflowNodeDefinition[];
};

function buildConnectionField(
  definition: WorkflowNodeDefinition,
  connections: WorkflowConnection[],
): WorkflowNodeTemplateField | null {
  if (!definition.connection_type) {
    return null;
  }

  const options = connections
    .filter(
      (connection) =>
        connection.enabled && connection.connection_type === definition.connection_type,
    )
    .map((connection) => ({
      label: connection.label,
      value: String(connection.id),
    }));

  return {
    help_text:
      options.length > 0
        ? 'Select a reusable connection for this node.'
        : 'No reusable connections are available for this app and scope yet.',
    key: 'connection_id',
    label: 'Connection',
    options: [
      {
        label: options.length > 0 ? 'Select a connection' : 'No connections available',
        value: '',
      },
      ...options,
    ],
    type: 'select',
  };
}

function enhanceDefinition(
  definition: WorkflowNodeDefinition,
  connections: WorkflowConnection[],
): WorkflowNodeDefinition {
  const fields = [...definition.fields];
  if (!fields.some((field) => field.key === 'connection_id')) {
    const connectionField = buildConnectionField(definition, connections);
    if (connectionField) {
      fields.unshift(connectionField);
    }
  }

  const config = { ...(definition.config ?? {}) };
  if (definition.connection_type && !Object.prototype.hasOwnProperty.call(config, 'connection_id')) {
    config.connection_id = '';
  }

  return {
    ...definition,
    category: definition.category || getNodeCategoryForKind(definition.kind),
    config,
    fields,
    typeVersion: definition.typeVersion ?? 1,
  };
}

function isChatModelDefinition(definition: WorkflowNodeDefinition): boolean {
  return Boolean(definition.is_model);
}

function normalizeCatalogSection(definition: WorkflowNodeDefinition): WorkflowNodeCatalogSection {
  if (definition.catalog_section) {
    return definition.catalog_section;
  }

  if (definition.kind === 'trigger') {
    return 'triggers';
  }

  if (definition.type === 'core.set') {
    return 'data';
  }

  if (definition.kind === 'agent' || definition.kind === 'condition' || definition.kind === 'response') {
    return 'flow';
  }

  return 'apps';
}

export function buildNodeRegistry(
  catalogDefinitions: WorkflowNodeDefinition[],
  connections: WorkflowConnection[],
  catalogSections: WorkflowCatalogSection[],
): WorkflowNodeRegistry {
  const definitions = catalogDefinitions.map((definition) => enhanceDefinition(definition, connections));
  const definitionMap = new Map(definitions.map((definition) => [definition.type, definition]));
  const sectionsById = new Map<WorkflowNodeCatalogSection, WorkflowPaletteSectionAccumulator>(
    catalogSections.map((section) => [
      section.id,
      {
        ...section,
        definitions: [],
      },
    ]),
  );
  definitions.forEach((definition) => {
    if (isChatModelDefinition(definition)) {
      return;
    }

    const section = sectionsById.get(normalizeCatalogSection(definition));
    if (!section) {
      return;
    }

    section.definitions.push(definition);
  });
  const paletteSections = catalogSections
    .map<WorkflowPaletteSection | null>((sectionId) => {
      const section = sectionsById.get(sectionId.id);
      if (!section || section.definitions.length === 0) {
        return null;
      }

      return {
        definitions: section.definitions,
        description: section.description,
        icon: section.icon,
        id: section.id,
        label: section.label,
      };
    })
    .filter((section): section is WorkflowPaletteSection => section !== null);

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
