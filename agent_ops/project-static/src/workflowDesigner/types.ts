export type WorkflowNodeTemplateOption = {
  label: string;
  value: string;
};

export type WorkflowNodeTemplateField = {
  help_text?: string;
  key: string;
  label: string;
  options?: WorkflowNodeTemplateOption[];
  placeholder?: string;
  rows?: number;
  type: 'text' | 'textarea' | 'select' | 'node_target';
};

export type WorkflowNodeTemplate = {
  category?: string;
  config?: Record<string, unknown>;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  kind: string;
  label: string;
};

export type WorkflowTriggerDefinition = {
  category?: string;
  config?: Record<string, unknown>;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  label: string;
  name: string;
};

export type WorkflowToolDefinition = {
  category?: string;
  config?: Record<string, unknown>;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  label: string;
  name: string;
};

export type WorkflowNode = {
  config?: Record<string, unknown>;
  id: string;
  kind: string;
  label: string;
  position: {
    x: number;
    y: number;
  };
};

export type WorkflowEdge = {
  id: string;
  source: string;
  target: string;
};

export type WorkflowDefinition = {
  edges: WorkflowEdge[];
  nodes: WorkflowNode[];
  viewport?: {
    x?: number;
    y?: number;
    zoom?: number;
  };
};

export type WorkflowSpecializedDefinition =
  | WorkflowToolDefinition
  | WorkflowTriggerDefinition;

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
