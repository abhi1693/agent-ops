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

const CHAT_MODEL_NODE_TYPES = new Set<string>([
  'tool.deepseek_chat_model',
  'tool.fireworks_chat_model',
  'tool.groq_chat_model',
  'tool.mistral_chat_model',
  'tool.openai_chat_model',
  'tool.openrouter_chat_model',
  'tool.xai_chat_model',
]);

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
    type: template.type,
    typeVersion: template.typeVersion ?? 1,
  };
}

function isChatModelDefinition(definition: WorkflowNodeDefinition): boolean {
  return CHAT_MODEL_NODE_TYPES.has(definition.type);
}

function getPaletteSectionMetadata(definition: WorkflowNodeDefinition): {
  description: string;
  icon?: string;
  id: string;
  label: string;
} {
  if (isChatModelDefinition(definition)) {
    return {
      description: 'Provider-backed chat completion models for agent nodes.',
      icon: 'mdi-message-processing-outline',
      id: 'chat_models',
      label: 'Chat Models',
    };
  }

  const appId = definition.app_id ?? 'builtins';
  return {
    description: definition.app_description ?? '',
    icon: definition.app_icon,
    id: appId,
    label: definition.app_label ?? definition.label,
  };
}

export function buildNodeRegistry(nodeTemplates: WorkflowNodeTemplate[]): WorkflowNodeRegistry {
  const definitions = nodeTemplates.map(createNodeDefinition);
  const definitionMap = new Map(definitions.map((definition) => [definition.type, definition]));
  const paletteSections = definitions.reduce<WorkflowPaletteSection[]>((sections, definition) => {
    const sectionMeta = getPaletteSectionMetadata(definition);
    let section = sections.find((item) => item.id === sectionMeta.id);
    if (!section) {
      section = {
        definitions: [],
        description: sectionMeta.description,
        icon: sectionMeta.icon,
        id: sectionMeta.id,
        label: sectionMeta.label,
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
