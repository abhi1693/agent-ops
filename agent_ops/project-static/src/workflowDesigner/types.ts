export type WorkflowNodeTemplateOption = {
  label: string;
  value: string;
};

export type WorkflowNodeTemplateField = {
  binding?: 'literal' | 'path' | 'template';
  help_text?: string;
  key: string;
  label: string;
  options?: WorkflowNodeTemplateOption[];
  options_by_field?: Record<string, Record<string, WorkflowNodeTemplateOption[]>>;
  placeholder?: string;
  rows?: number;
  type: 'text' | 'textarea' | 'select' | 'node_target';
  ui_group?: 'advanced' | 'input' | 'result';
  visible_when?: Record<string, string[]>;
};

export type WorkflowNodeCatalogSection = 'triggers' | 'flow' | 'data' | 'apps';

export type WorkflowNodeTemplate = {
  app_description?: string;
  app_icon?: string;
  app_id?: string;
  app_label?: string;
  catalog_section?: WorkflowNodeCatalogSection;
  category?: string;
  config?: Record<string, unknown>;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  kind: string;
  label: string;
  type: string;
  typeVersion?: number;
};

export type WorkflowNodeKind = 'trigger' | 'agent' | 'tool' | 'condition' | 'response';

export type WorkflowNodeCategoryId =
  | 'entry_point'
  | 'processing'
  | 'control_flow'
  | 'outcome';

export type WorkflowNodeCategory = {
  description: string;
  id: WorkflowNodeCategoryId;
  label: string;
};

export type WorkflowNodeDefinition = {
  app_description?: string;
  app_icon?: string;
  app_id?: string;
  app_label?: string;
  catalog_section?: WorkflowNodeCatalogSection;
  category: WorkflowNodeCategoryId;
  config?: Record<string, unknown>;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  kind: WorkflowNodeKind | string;
  label: string;
  type: string;
  typeVersion: number;
};

export type WorkflowPaletteSection = {
  definitions: WorkflowNodeDefinition[];
  description: string;
  icon?: string;
  id: string;
  label: string;
};

export type WorkflowPersistedNode = {
  config?: Record<string, unknown>;
  id: string;
  kind: string;
  label: string;
  position: {
    x: number;
    y: number;
  };
  type: string;
  typeVersion?: number;
};

export type WorkflowNode = WorkflowPersistedNode & {
  type: string;
  typeVersion: number;
};

export type WorkflowPersistedEdge = {
  id: string;
  label?: string;
  source: string;
  sourcePort?: string;
  target: string;
  targetPort?: string;
};

export type WorkflowEdge = WorkflowPersistedEdge;

export type WorkflowPersistedDefinition = {
  edges: WorkflowPersistedEdge[];
  nodes: WorkflowPersistedNode[];
  viewport?: {
    x?: number;
    y?: number;
    zoom?: number;
  };
};

export type WorkflowDefinition = {
  edges: WorkflowEdge[];
  nodes: WorkflowNode[];
  viewport?: WorkflowPersistedDefinition['viewport'];
};

export type DesignerElements = {
  advancedPanel: HTMLDetailsElement;
  board: HTMLElement;
  canvas: HTMLElement;
  canvasEmpty: HTMLElement;
  definitionInput: HTMLInputElement | HTMLTextAreaElement;
  deleteNodeButton: HTMLButtonElement;
  edgeCount: HTMLElement;
  edgeCountLabel: HTMLElement;
  edgeEmpty: HTMLElement;
  edgeList: HTMLElement;
  edgesSvg: SVGSVGElement;
  nodeCount: HTMLElement;
  nodeConfig: HTMLTextAreaElement;
  nodeEmpty: HTMLElement;
  nodeFields: HTMLElement;
  nodeKind: HTMLSelectElement;
  nodeLabel: HTMLInputElement;
  nodePalette: HTMLElement;
  nodeTemplateFields: HTMLElement;
  selectedNodeSummary: HTMLElement;
  selectedTemplate: HTMLElement;
  surface: HTMLElement;
};
