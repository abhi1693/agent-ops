import { getNodeCategoryForKind } from './categories';
import { getCatalogSectionForDefinition } from './nodeSemantics';
import type {
  WorkflowConnection,
  WorkflowCatalogSection,
  WorkflowNodeCatalogSection,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowPaletteSection,
} from '../types';

export type WorkflowNodeRegistry = {
  definitions: WorkflowNodeDefinition[];
  definitionMap: Map<string, WorkflowNodeDefinition>;
  paletteSections: WorkflowPaletteSection[];
};

type WorkflowPaletteSectionAccumulator = WorkflowCatalogSection & {
  definitions: WorkflowNodeDefinition[];
};

function enhanceDefinition(
  definition: WorkflowNodeDefinition,
  connections: WorkflowConnection[],
): WorkflowNodeDefinition {
  const config = { ...(definition.config ?? {}) };
  void connections;
  (definition.connection_slots ?? []).forEach((slot) => {
    if (!Object.prototype.hasOwnProperty.call(config, slot.key)) {
      config[slot.key] = slot.multiple ? [] : '';
    }
  });

  return {
    ...definition,
    category: definition.category || getNodeCategoryForKind(definition.kind),
    config,
    fields: [...definition.fields],
    typeVersion: definition.typeVersion ?? 1,
  };
}

function isChatModelDefinition(definition: WorkflowNodeDefinition): boolean {
  return Boolean(definition.is_model);
}

function normalizeCatalogSection(definition: WorkflowNodeDefinition): WorkflowNodeCatalogSection {
  return getCatalogSectionForDefinition(definition);
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
  void definition;

  return registry.paletteSections
    .map((section) => ({
      ...section,
      definitions: section.definitions,
    }))
    .filter((section) => section.definitions.length > 0);
}
