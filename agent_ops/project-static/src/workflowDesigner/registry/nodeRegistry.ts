import { getNodeCategoryForKind } from './categories';
import type {
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

function createNodeDefinition(template: WorkflowNodeTemplate): WorkflowNodeDefinition {
  return {
    app_description: template.app_description,
    app_icon: template.app_icon,
    app_id: template.app_id,
    app_label: template.app_label,
    category: getNodeCategoryForKind(template.kind),
    config: template.config,
    description: template.description,
    fields: template.fields,
    icon: template.icon,
    kind: template.kind,
    label: template.label,
    operation: template.operation,
    resource: template.resource,
    type: template.type,
    typeVersion: template.typeVersion ?? 1,
  };
}

export function buildNodeRegistry(nodeTemplates: WorkflowNodeTemplate[]): WorkflowNodeRegistry {
  const definitions = nodeTemplates.map(createNodeDefinition);
  const definitionMap = new Map(definitions.map((definition) => [definition.type, definition]));
  const paletteSections = definitions.reduce<WorkflowPaletteSection[]>((sections, definition) => {
    const appId = definition.app_id ?? 'builtins';
    let section = sections.find((item) => item.id === appId);
    if (!section) {
      section = {
        definitions: [],
        description: definition.app_description ?? '',
        icon: definition.app_icon,
        id: appId,
        label: definition.app_label ?? definition.label,
      };
      sections.push(section);
    }
    section.definitions.push(definition);
    return sections;
  }, []);

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
