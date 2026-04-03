import type { WorkflowNodeDefinition } from '../types';

export function isModelDefinition(
  definition: Pick<WorkflowNodeDefinition, 'is_model'> | null | undefined,
): boolean {
  return Boolean(definition?.is_model);
}

export function isToolCompatibleDefinition(
  definition: Pick<WorkflowNodeDefinition, 'is_model' | 'kind'>,
): boolean {
  return definition.kind === 'tool' && !isModelDefinition(definition);
}
