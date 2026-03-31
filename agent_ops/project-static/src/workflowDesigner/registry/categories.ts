import type {
  WorkflowNodeCategory,
  WorkflowNodeCategoryId,
  WorkflowNodeKind,
} from '../types';

export const WORKFLOW_NODE_CATEGORY_ORDER: WorkflowNodeCategoryId[] = [
  'entry_point',
  'processing',
  'control_flow',
  'outcome',
];

export const WORKFLOW_NODE_CATEGORIES: Record<WorkflowNodeCategoryId, WorkflowNodeCategory> = {
  entry_point: {
    id: 'entry_point',
    label: 'Entry point',
    description: 'Choose how execution begins.',
  },
  processing: {
    id: 'processing',
    label: 'Processing',
    description: 'Transform context or call external systems.',
  },
  control_flow: {
    id: 'control_flow',
    label: 'Control flow',
    description: 'Route execution through branches.',
  },
  outcome: {
    id: 'outcome',
    label: 'Outcome',
    description: 'Close the workflow with a final response.',
  },
};

export function getNodeCategoryForKind(kind: WorkflowNodeKind | string): WorkflowNodeCategoryId {
  if (kind === 'trigger') {
    return 'entry_point';
  }

  if (kind === 'condition') {
    return 'control_flow';
  }

  if (kind === 'response') {
    return 'outcome';
  }

  return 'processing';
}
