export type WorkflowNodeTemplateOption = {
  label: string;
  value: string;
};

export type WorkflowNodeTemplateCollectionOption = {
  description?: string;
  fields: WorkflowNodeTemplateField[];
  key: string;
  label: string;
  multiple?: boolean;
};

export type WorkflowNodeTemplateField = {
  binding?: 'literal' | 'path' | 'template';
  collection_options?: WorkflowNodeTemplateCollectionOption[];
  default?: unknown;
  description?: string;
  display_options?: Record<string, Record<string, string[]>>;
  help_text?: string;
  hint?: string;
  is_node_setting?: boolean;
  key: string;
  label: string;
  no_data_expression?: boolean;
  options?: WorkflowNodeTemplateOption[];
  options_by_field?: Record<string, Record<string, WorkflowNodeTemplateOption[]>>;
  placeholder?: string;
  required?: boolean;
  requires_data_path?: 'single' | 'multiple';
  rows?: number;
  type: 'text' | 'textarea' | 'select' | 'node_target' | 'fixed_collection';
  ui_group?: 'advanced' | 'input' | 'result';
  value_type?: string;
  visible_when?: Record<string, string[]>;
};

export type WorkflowNodeCatalogSection = string;
export type WorkflowCatalogGroupId = string;

export type WorkflowCatalogSection = {
  description: string;
  icon?: string;
  id: WorkflowNodeCatalogSection;
  label: string;
};

export type WorkflowCatalogGroup = {
  description: string;
  icon?: string;
  id: WorkflowCatalogGroupId;
  label: string;
};

export type WorkflowExecutionStatusPresentation = {
  badge_class: string;
  label: string;
};

export type WorkflowChromePresentation = {
  browser: {
    aria_label: string;
    close_label: string;
    default_title: string;
    search_label: string;
  };
  canvas: {
    controls_aria_label: string;
    empty_state: {
      action_aria_label: string;
      action_caption: string;
      action_label: string;
    };
    zoom: {
      fit: string;
      zoom_in: string;
      zoom_out: string;
    };
  };
  execution_panel: {
    aria_label: string;
    context_label: string;
    description: string;
    empty: string;
    output_label: string;
    title: string;
    trace_label: string;
  };
  settings_panel: {
    aria_label: string;
    close_label: string;
    input_description: string;
    input_title: string;
    output_description: string;
    output_title: string;
    settings_empty: string;
    settings_tab: string;
    parameters_tab: string;
    title: string;
  };
  toolbar: {
    add_node: string;
    back_label: string;
    run_workflow: string;
    settings: string;
  };
};

export type WorkflowExecutionPresentation = {
  default_status: WorkflowExecutionStatusPresentation;
  inspector: {
    overview: {
      active_nodes: string;
      failed_nodes: string;
      idle_value: string;
      last_completed_node: string;
      mode: string;
      selected_node: string;
      skipped_nodes: string;
      step_count: string;
      trigger_mode: string;
      workflow_version: string;
    };
    steps: {
      empty: string;
      next_node_label: string;
      result_label: string;
      title: string;
    };
    tabs: {
      context: string;
      input: string;
      output: string;
      overview: string;
      steps: string;
      trace: string;
    };
  };
  messages: {
    execution_failed: string;
    poll_timeout: string;
    status_fetch_failed: string;
  };
  result_labels: {
    node_run: string;
    workflow_run: string;
  };
  run_button: {
    idle: string;
    running: string;
  };
  running_status: {
    node: string;
    workflow: string;
  };
  statuses: Record<string, WorkflowExecutionStatusPresentation>;
};

export type WorkflowSettingsGroupPresentation = {
  description: string;
  fields?: Record<string, string>;
  title: string;
};

export type WorkflowSettingsPresentation = {
  controls: {
    expression_hint: string;
    required_badge: string;
    mode_expression: string;
    mode_static: string;
    mode_suffix: string;
    select_placeholder: string;
  };
  empty: string;
  groups: Record<string, WorkflowSettingsGroupPresentation>;
};

export type WorkflowNodeSelectionPresentation = {
  app_actions: {
    action_meta: string;
    empty: string;
    search_placeholder: string;
    title: string;
  };
  app_details: {
    default_title: string;
    empty: string;
    sections: {
      actions: string;
      triggers: string;
    };
  };
  category_details: {
    empty_template: string;
    fallback_empty: string;
    search_placeholder: string;
  };
  common: {
    add_description: string;
    connect_description: string;
    default_empty: string;
    default_search_placeholder: string;
    default_title: string;
  };
  insert: {
    model_provider: {
      description: string;
      empty: string;
      search_placeholder: string;
      title: string;
    };
    tool: {
      description: string;
      empty: string;
      search_placeholder: string;
      title: string;
    };
  };
  next_step_root: {
    empty: string;
    items: {
      app_action: {
        description: string;
        label: string;
      };
    };
    search_placeholder: string;
    title: string;
  };
  trigger_apps: {
    empty: string;
    search_placeholder: string;
    title: string;
    trigger_meta: string;
  };
  trigger_root: {
    additional: {
      description: string;
      label: string;
    };
    empty: string;
    initial: {
      description: string;
      title: string;
    };
    items: {
      app_event: {
        description: string;
      };
      manual: {
        label: string;
      };
      schedule: {
        label: string;
      };
    };
    search_placeholder: string;
  };
};

export type WorkflowCatalogPresentation = {
  chrome: WorkflowChromePresentation;
  execution: WorkflowExecutionPresentation;
  node_selection: WorkflowNodeSelectionPresentation;
  settings: WorkflowSettingsPresentation;
};

export type WorkflowNodeTemplate = {
  app_description?: string;
  app_icon?: string;
  app_id?: string;
  app_label?: string;
  group?: WorkflowCatalogGroupId;
  catalog_section?: WorkflowNodeCatalogSection;
  category?: string;
  config?: Record<string, unknown>;
  defaultColor?: string | null;
  defaultName?: string | null;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  kind: string;
  label: string;
  type: string;
  typeVersion?: number;
  subtitle?: string | null;
  nodeGroup?: string[];
};

export type WorkflowCatalogPayload = {
  groups: WorkflowCatalogGroup[];
  definitions: WorkflowNodeDefinition[];
  presentation: WorkflowCatalogPresentation;
  sections: WorkflowCatalogSection[];
};

export type WorkflowConnection = {
  connection_type: string;
  edit_url: string;
  enabled: boolean;
  id: number;
  integration_id: string;
  label: string;
  name: string;
  oauth_connect_url?: string;
  oauth_connected?: boolean;
  scope_label?: string;
  supports_oauth?: boolean;
};

export type AgentAuxiliaryPortId = 'ai_languageModel' | 'ai_tool';
export type ConnectorSide = 'top' | 'right' | 'bottom' | 'left';
export type Point = {
  x: number;
  y: number;
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
  group?: WorkflowCatalogGroupId;
  capabilities?: string[];
  catalog_section?: WorkflowNodeCatalogSection;
  category: WorkflowNodeCategoryId;
  config?: Record<string, unknown>;
  connection_slots?: Array<{
    allowed_connection_types: string[];
    description?: string;
    key: string;
    label: string;
    multiple?: boolean;
    required?: boolean;
  }>;
  connection_type?: string | null;
  defaultColor?: string | null;
  defaultName?: string | null;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  is_model?: boolean;
  kind: WorkflowNodeKind | string;
  label: string;
  mode?: string;
  nodeGroup?: string[];
  operation?: string;
  resource?: string;
  subtitle?: string | null;
  tags?: string[];
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
  connections?: Record<string, string | number | Array<string | number>>;
  id: string;
  kind?: string;
  label?: string;
  name?: string;
  connection_id?: string | number;
  parameters?: Record<string, unknown>;
  notes?: string;
  disabled?: boolean;
  ui?: Record<string, unknown>;
  position: {
    x: number;
    y: number;
  };
  type: string;
  typeVersion?: number;
};

export type WorkflowNode = Omit<
  WorkflowPersistedNode,
  'kind' | 'label' | 'name' | 'parameters' | 'connection_id' | 'connections'
> & {
  config: Record<string, unknown>;
  kind: string;
  label: string;
  type: string;
  typeVersion: number;
};

export type WorkflowAgentAuxiliaryPort = {
  id: AgentAuxiliaryPortId;
  label: string;
};

export type WorkflowConnectionHoverTarget = {
  nodeId: string;
  side: ConnectorSide;
  targetPort: AgentAuxiliaryPortId | null;
};

export type WorkflowEditorNodeConnector = {
  isCandidate: boolean;
  isInputActive: boolean;
  isOutputActive: boolean;
  modeClass: string;
  nodeId: string;
  side: ConnectorSide;
};

export type WorkflowEditorAuxiliaryPort = {
  actionIcon: string;
  ariaLabel: string;
  id: AgentAuxiliaryPortId;
  isActive: boolean;
  isCandidate: boolean;
  isConnected: boolean;
  isWarning: boolean;
  label: string;
  modelProviderAppId?: string;
  nodeId: string;
  stateLabel: string;
  title: string;
};

export type WorkflowEditorNodePresentation = {
  agentDisplayTitle: string;
  agentNeedsModel: boolean;
  auxiliaryPorts: WorkflowEditorAuxiliaryPort[];
  canToggleDisabled: boolean;
  connectors: WorkflowEditorNodeConnector[];
  executionStatusLabel: string | null;
  executionStatusTone: 'completed' | 'current' | 'failed' | 'running' | 'skipped' | null;
  icon: string;
  isConnectionCandidate: boolean;
  isConnectionSource: boolean;
  isConnectionTarget: boolean;
  isExecutionCompleted: boolean;
  isExecutionCurrent: boolean;
  isDisabled: boolean;
  isExecutionFailed: boolean;
  isExecutionPending: boolean;
  isExecutionSkipped: boolean;
  isSelected: boolean;
  node: WorkflowNode;
  showAgentKindLabel: boolean;
  title: string;
};

export type WorkflowEditorRenderedEdge = {
  id: string;
  isHovered: boolean;
  path: string;
};

export type WorkflowEditorEdgeControl = {
  edgeId: string;
  x: number;
  y: number;
};

export type WorkflowEditorEdgesPresentation = {
  draftPath: string | null;
  edges: WorkflowEditorRenderedEdge[];
  hoveredControl: WorkflowEditorEdgeControl | null;
};

export type WorkflowPersistedEdge = {
  id: string;
  label?: string;
  source: string;
  source_port?: string;
  sourcePort?: string;
  target: string;
  target_port?: string;
  targetPort?: string;
};

export type WorkflowEdge = WorkflowPersistedEdge;

export type WorkflowPersistedDefinition = {
  definition_version?: number;
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
