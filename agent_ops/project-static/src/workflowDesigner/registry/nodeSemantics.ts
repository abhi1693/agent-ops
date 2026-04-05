import type { WorkflowNodeDefinition } from '../types';

export const TRIGGER_WEBHOOK_CAPABILITY = 'trigger:webhook';
export const TRIGGER_MANUAL_CAPABILITY = 'trigger:manual';
export const TRIGGER_SCHEDULE_CAPABILITY = 'trigger:schedule';

type CapabilityDefinitionLike = Pick<WorkflowNodeDefinition, 'capabilities'> | null | undefined;
type DefinitionLike = Pick<WorkflowNodeDefinition, 'capabilities' | 'catalog_section' | 'group' | 'kind'> | null | undefined;

export function hasNodeCapability(
  definition: CapabilityDefinitionLike,
  capability: string,
): boolean {
  return Boolean(definition?.capabilities?.includes(capability));
}

export function isWebhookTriggerDefinition(definition: CapabilityDefinitionLike): boolean {
  return hasNodeCapability(definition, TRIGGER_WEBHOOK_CAPABILITY);
}

export function isManualTriggerDefinition(definition: CapabilityDefinitionLike): boolean {
  return hasNodeCapability(definition, TRIGGER_MANUAL_CAPABILITY);
}

export function isScheduleTriggerDefinition(definition: CapabilityDefinitionLike): boolean {
  return hasNodeCapability(definition, TRIGGER_SCHEDULE_CAPABILITY);
}

export function getCatalogSectionForDefinition(definition: DefinitionLike): string {
  const configuredSection = definition?.catalog_section?.trim();
  if (configuredSection) {
    return configuredSection;
  }

  if (definition?.kind === 'trigger') {
    return 'triggers';
  }

  if (definition?.group === 'data') {
    return 'data';
  }

  if (definition?.kind === 'agent' || definition?.kind === 'condition' || definition?.kind === 'response') {
    return 'flow';
  }

  return 'apps';
}
