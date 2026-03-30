type WorkflowNodeTemplateOption = {
  label: string;
  value: string;
};

type WorkflowNodeTemplateField = {
  help_text?: string;
  key: string;
  label: string;
  options?: WorkflowNodeTemplateOption[];
  placeholder?: string;
  rows?: number;
  type: 'text' | 'textarea' | 'select' | 'node_target';
};

type WorkflowNodeTemplate = {
  category?: string;
  config?: Record<string, unknown>;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  kind: string;
  label: string;
};

type WorkflowTriggerDefinition = {
  category?: string;
  config?: Record<string, unknown>;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  label: string;
  name: string;
};

type WorkflowToolDefinition = {
  category?: string;
  config?: Record<string, unknown>;
  description: string;
  fields: WorkflowNodeTemplateField[];
  icon?: string;
  label: string;
  name: string;
};

type WorkflowNode = {
  config?: Record<string, unknown>;
  id: string;
  kind: string;
  label: string;
  position: {
    x: number;
    y: number;
  };
};

type WorkflowEdge = {
  id: string;
  source: string;
  target: string;
};

type WorkflowDefinition = {
  edges: WorkflowEdge[];
  nodes: WorkflowNode[];
  viewport?: {
    x?: number;
    y?: number;
    zoom?: number;
  };
};

type DesignerElements = {
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

const NODE_WIDTH = 232;
const NODE_HEIGHT = 108;
const NODE_COLUMN_GAP = 264;
const NODE_ROW_GAP = 148;
const SURFACE_PADDING = 96;
const DEFAULT_SURFACE_HEIGHT = 680;

function parseJsonScript<T>(scriptId: string, fallback: T): T {
  const script = document.getElementById(scriptId);
  if (!script || !script.textContent) {
    return fallback;
  }

  try {
    return JSON.parse(script.textContent) as T;
  } catch (error) {
    console.error(error);
    return fallback;
  }
}

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function normalizeDefinition(value: unknown): WorkflowDefinition {
  if (!value || typeof value !== 'object') {
    return { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } };
  }

  const maybeDefinition = value as Partial<WorkflowDefinition>;
  return {
    nodes: Array.isArray(maybeDefinition.nodes) ? maybeDefinition.nodes : [],
    edges: Array.isArray(maybeDefinition.edges) ? maybeDefinition.edges : [],
    viewport: maybeDefinition.viewport ?? { x: 0, y: 0, zoom: 1 },
  };
}

function createId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function getNodeTitle(node: WorkflowNode): string {
  return node.label || node.kind;
}

function formatKindLabel(kind: string): string {
  return kind
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function stringifyConfigValue(value: unknown, pretty = false): string {
  if (value === undefined || value === null) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, pretty ? 2 : 0);
    } catch (error) {
      console.error(error);
    }
  }

  return String(value);
}

function getConfigString(
  config: Record<string, unknown> | undefined,
  key: string,
  prettyJson = false,
): string {
  const value = config?.[key];
  return stringifyConfigValue(value, prettyJson);
}

function getTriggerType(config: Record<string, unknown> | undefined): string {
  const triggerType = getConfigString(config, 'type');
  if (triggerType) {
    return triggerType;
  }
  return 'manual';
}

function getToolName(config: Record<string, unknown> | undefined): string {
  const toolName = getConfigString(config, 'tool_name');
  if (toolName) {
    return toolName;
  }

  const legacyOperation = getConfigString(config, 'operation');
  if (legacyOperation) {
    return legacyOperation;
  }

  return 'passthrough';
}

function formatCount(value: number, singular: string, plural = `${singular}s`): string {
  return `${value} ${value === 1 ? singular : plural}`;
}

function isNodeDisabled(node: WorkflowNode | undefined): boolean {
  return Boolean(node?.config && node.config['disabled']);
}

function getNodeStatusLabel(node: WorkflowNode | undefined, isRunning = false): string {
  if (!node) {
    return 'Idle';
  }
  if (isRunning) {
    return 'Running';
  }
  if (isNodeDisabled(node)) {
    return 'Disabled';
  }
  return 'Ready';
}

function getNodeSubtitle(
  node: WorkflowNode,
  triggerDefinitionMap: Map<string, WorkflowTriggerDefinition>,
  toolDefinitionMap: Map<string, WorkflowToolDefinition>,
): string {
  if (node.kind === 'trigger') {
    return triggerDefinitionMap.get(getTriggerType(node.config))?.label ?? 'Workflow entry point';
  }

  if (node.kind === 'tool') {
    return toolDefinitionMap.get(getToolName(node.config))?.label ?? 'Runs a workflow tool';
  }

  if (node.kind === 'condition') {
    const path = getConfigString(node.config, 'path');
    const operator = getConfigString(node.config, 'operator');
    if (path && operator) {
      return `${path} • ${formatKindLabel(operator)}`;
    }
    if (path) {
      return path;
    }
    return 'Branches workflow execution';
  }

  if (node.kind === 'response') {
    const status = getConfigString(node.config, 'status');
    return status ? `Marks run as ${status.replace(/_/g, ' ')}` : 'Completes the workflow';
  }

  if (node.kind === 'agent') {
    const outputKey = getConfigString(node.config, 'output_key');
    return outputKey ? `Writes to ${outputKey}` : 'Writes a message into workflow context';
  }

  return 'Custom workflow node';
}

function initWorkflowDesigner(): void {
  const root = document.querySelector<HTMLElement>('[data-workflow-designer]');
  if (!root) {
    return;
  }

  const definitionInput = root.querySelector<HTMLInputElement | HTMLTextAreaElement>('#id_definition');
  const canvas = root.querySelector<HTMLElement>('[data-workflow-canvas]');
  const canvasEmpty = root.querySelector<HTMLElement>('[data-canvas-empty]');
  const surface = root.querySelector<HTMLElement>('[data-workflow-surface]');
  const board = root.querySelector<HTMLElement>('[data-workflow-board]');
  const edgesSvg = root.querySelector<SVGSVGElement>('[data-workflow-edges]');
  const nodeCount = root.querySelector<HTMLElement>('[data-node-count]');
  const edgeCount = root.querySelector<HTMLElement>('[data-edge-count]');
  const edgeCountLabel = root.querySelector<HTMLElement>('[data-edge-count-label]');
  const selectedNodeSummary = root.querySelector<HTMLElement>('[data-selected-node-summary]');
  const nodePalette = root.querySelector<HTMLElement>('[data-node-palette]');
  const nodeEmpty = root.querySelector<HTMLElement>('[data-node-empty]');
  const nodeFields = root.querySelector<HTMLElement>('[data-node-fields]');
  const nodeLabel = root.querySelector<HTMLInputElement>('[data-field="label"]');
  const nodeKind = root.querySelector<HTMLSelectElement>('[data-field="kind"]');
  const selectedTemplate = root.querySelector<HTMLElement>('[data-selected-template]');
  const nodeTemplateFields = root.querySelector<HTMLElement>('[data-node-template-fields]');
  const nodeConfig = root.querySelector<HTMLTextAreaElement>('[data-field="config"]');
  const advancedPanel = root.querySelector<HTMLDetailsElement>('[data-advanced-panel]');
  const deleteNodeButton = root.querySelector<HTMLButtonElement>('[data-delete-node]');
  const edgeList = root.querySelector<HTMLElement>('[data-edge-list]');
  const edgeEmpty = root.querySelector<HTMLElement>('[data-edge-empty]');

  if (
    !definitionInput ||
    !canvas ||
    !canvasEmpty ||
    !surface ||
    !board ||
    !edgesSvg ||
    !nodeCount ||
    !edgeCount ||
    !edgeCountLabel ||
    !selectedNodeSummary ||
    !nodePalette ||
    !nodeEmpty ||
    !nodeFields ||
    !nodeLabel ||
    !nodeKind ||
    !selectedTemplate ||
    !nodeTemplateFields ||
    !nodeConfig ||
    !advancedPanel ||
    !deleteNodeButton ||
    !edgeList ||
    !edgeEmpty
  ) {
    return;
  }

  const elements: DesignerElements = {
    advancedPanel,
    board,
    canvas,
    canvasEmpty,
    definitionInput,
    deleteNodeButton,
    edgeCount,
    edgeCountLabel,
    edgeEmpty,
    edgeList,
    edgesSvg,
    nodeCount,
    nodeConfig,
    nodeEmpty,
    nodeFields,
    nodeKind,
    nodeLabel,
    nodePalette,
    nodeTemplateFields,
    selectedNodeSummary,
    selectedTemplate,
    surface,
  };

  const definition = normalizeDefinition(parseJsonScript<WorkflowDefinition>('workflow-definition-data', { nodes: [], edges: [] }));
  const nodeTemplates = parseJsonScript<WorkflowNodeTemplate[]>('workflow-node-templates-data', []);
  const triggerDefinitions = parseJsonScript<WorkflowTriggerDefinition[]>('workflow-trigger-definitions-data', []);
  const toolDefinitions = parseJsonScript<WorkflowToolDefinition[]>('workflow-tool-definitions-data', []);
  const templateMap = new Map(nodeTemplates.map((template) => [template.kind, template]));
  const triggerDefinitionMap = new Map(triggerDefinitions.map((triggerDefinition) => [triggerDefinition.name, triggerDefinition]));
  const toolDefinitionMap = new Map(toolDefinitions.map((toolDefinition) => [toolDefinition.name, toolDefinition]));

  let selectedNodeId: string | null = definition.nodes[0]?.id ?? null;
  let dragState:
    | {
        id: string;
        offsetX: number;
        offsetY: number;
      }
    | null = null;
  let quickAddSourceId: string | null = null;
  let runningNodeId: string | null = null;
  let connectionDraft:
    | {
        pointerX: number;
        pointerY: number;
        sourceId: string;
      }
    | null = null;

  function syncDefinition(): void {
    elements.definitionInput.value = JSON.stringify(definition);
  }

  function getNode(nodeId: string | null): WorkflowNode | undefined {
    if (!nodeId) {
      return undefined;
    }

    return definition.nodes.find((node) => node.id === nodeId);
  }

  function getNodeTemplate(node: WorkflowNode | undefined): WorkflowNodeTemplate | undefined {
    if (!node) {
      return undefined;
    }

    return templateMap.get(node.kind);
  }

  function getTriggerDefinition(node: WorkflowNode | undefined): WorkflowTriggerDefinition | undefined {
    if (!node || node.kind !== 'trigger') {
      return undefined;
    }

    return triggerDefinitionMap.get(getTriggerType(node.config));
  }

  function getToolDefinition(node: WorkflowNode | undefined): WorkflowToolDefinition | undefined {
    if (!node || node.kind !== 'tool') {
      return undefined;
    }

    return toolDefinitionMap.get(getToolName(node.config));
  }

  function updateSurfaceSize(): void {
    const maxX = definition.nodes.reduce((value, node) => Math.max(value, node.position.x + NODE_WIDTH), 0);
    const maxY = definition.nodes.reduce((value, node) => Math.max(value, node.position.y + NODE_HEIGHT), 0);
    const width = Math.max(elements.board.clientWidth, maxX + SURFACE_PADDING);
    const height = Math.max(DEFAULT_SURFACE_HEIGHT, maxY + SURFACE_PADDING);

    elements.surface.style.width = `${width}px`;
    elements.surface.style.height = `${height}px`;
  }

  function renderBoardSummary(): void {
    const selectedNode = getNode(selectedNodeId);
    elements.nodeCount.textContent = String(definition.nodes.length);
    elements.edgeCount.textContent = String(definition.edges.length);
    elements.edgeCountLabel.textContent = formatCount(definition.edges.length, 'link');
    elements.selectedNodeSummary.textContent = selectedNode ? getNodeTitle(selectedNode) : 'None';
  }

  function renderCanvasState(): void {
    const isEmpty = definition.nodes.length === 0;
    elements.canvasEmpty.classList.toggle('d-none', !isEmpty);
    elements.board.classList.toggle('is-empty', isEmpty);
  }

  function syncAdvancedConfigEditor(): void {
    const selectedNode = getNode(selectedNodeId);
    elements.nodeConfig.value = JSON.stringify(selectedNode?.config ?? {}, null, 2);
  }

  function getFieldValue(node: WorkflowNode, field: WorkflowNodeTemplateField): string {
    if (node.kind === 'trigger' && field.key === 'type') {
      return getTriggerType(node.config);
    }
    if (node.kind === 'tool' && field.key === 'tool_name') {
      return getToolName(node.config);
    }

    return getConfigString(node.config, field.key, field.type === 'textarea');
  }

  function renderSelectedTemplate(node: WorkflowNode | undefined, template: WorkflowNodeTemplate | undefined): void {
    if (!node) {
      elements.selectedTemplate.innerHTML = '';
      return;
    }

    const icon = template?.icon ?? 'mdi-vector-square';
    const title = template?.label ?? formatKindLabel(node.kind);
    const description =
      template?.description ??
      'Custom node. Use the advanced runtime JSON editor to configure fields that are not mapped into the inspector.';

    elements.selectedTemplate.innerHTML = `
      <div class="workflow-selected-template-card workflow-selected-template-card--compact${template ? '' : ' is-custom'}">
        <span class="workflow-selected-template-icon">
          <i class="mdi ${escapeHtml(icon)}"></i>
        </span>
        <div class="workflow-selected-template-copy">
          <div class="workflow-selected-template-title">${escapeHtml(title)}</div>
          <div class="workflow-selected-template-description">${escapeHtml(description)}</div>
        </div>
      </div>
    `;
  }

  function renderFieldMarkup(fields: WorkflowNodeTemplateField[], node: WorkflowNode): string {
    const nodeTargetOptions = definition.nodes
      .filter((candidate) => candidate.id !== node.id)
      .map(
        (candidate) =>
          `<option value="${escapeHtml(candidate.id)}">${escapeHtml(getNodeTitle(candidate))}</option>`,
      )
      .join('');

    return fields
      .map((field) => {
        const fieldValue = getFieldValue(node, field);
        const currentValue = escapeHtml(fieldValue);
        const helpText = field.help_text
          ? `<div class="form-hint">${escapeHtml(field.help_text)}</div>`
          : '';

        if (field.type === 'textarea') {
          return `
            <div>
              <label class="form-label" for="workflow-config-${escapeHtml(field.key)}">${escapeHtml(field.label)}</label>
              <textarea
                id="workflow-config-${escapeHtml(field.key)}"
                class="form-control"
                rows="${field.rows ?? 4}"
                placeholder="${escapeHtml(field.placeholder ?? '')}"
                data-config-field="${escapeHtml(field.key)}"
              >${currentValue}</textarea>
              ${helpText}
            </div>
          `;
        }

        if (field.type === 'select') {
          const options = (field.options ?? [])
            .map((option) => {
              const selected = option.value === fieldValue ? ' selected' : '';
              return `<option value="${escapeHtml(option.value)}"${selected}>${escapeHtml(option.label)}</option>`;
            })
            .join('');

          return `
            <div>
              <label class="form-label" for="workflow-config-${escapeHtml(field.key)}">${escapeHtml(field.label)}</label>
              <select
                id="workflow-config-${escapeHtml(field.key)}"
                class="form-select"
                data-config-field="${escapeHtml(field.key)}"
              >
                ${options}
              </select>
              ${helpText}
            </div>
          `;
        }

        if (field.type === 'node_target') {
          return `
            <div>
              <label class="form-label" for="workflow-config-${escapeHtml(field.key)}">${escapeHtml(field.label)}</label>
              <select
                id="workflow-config-${escapeHtml(field.key)}"
                class="form-select"
                data-config-field="${escapeHtml(field.key)}"
              >
                <option value="">Choose a connected node</option>
                ${nodeTargetOptions}
              </select>
              ${helpText}
            </div>
          `;
        }

        return `
          <div>
            <label class="form-label" for="workflow-config-${escapeHtml(field.key)}">${escapeHtml(field.label)}</label>
            <input
              id="workflow-config-${escapeHtml(field.key)}"
              class="form-control"
              type="text"
              value="${currentValue}"
              placeholder="${escapeHtml(field.placeholder ?? '')}"
              data-config-field="${escapeHtml(field.key)}"
            >
            ${helpText}
          </div>
        `;
      })
      .join('');
  }

  function syncRenderedFieldValues(fields: WorkflowNodeTemplateField[], node: WorkflowNode): void {
    fields.forEach((field) => {
      if (field.type !== 'node_target') {
        return;
      }

      const targetSelect = elements.nodeTemplateFields.querySelector<HTMLSelectElement>(
        `[data-config-field="${field.key}"]`,
      );
      if (targetSelect) {
        targetSelect.value = getFieldValue(node, field);
      }
    });
  }

  function renderTemplateFields(node: WorkflowNode | undefined, template: WorkflowNodeTemplate | undefined): void {
    if (!node || !template) {
      elements.nodeTemplateFields.innerHTML = '';
      return;
    }

    const toolDefinition = getToolDefinition(node);
    const triggerDefinition = getTriggerDefinition(node);
    const specializedDefinition = node.kind === 'tool' ? toolDefinition : node.kind === 'trigger' ? triggerDefinition : undefined;
    const specializedSection = (node.kind === 'tool' || node.kind === 'trigger')
      ? specializedDefinition
        ? `
          <div class="workflow-selected-template-card workflow-tool-definition-card mt-3">
            <span class="workflow-selected-template-icon">
              <i class="mdi ${escapeHtml(specializedDefinition.icon ?? 'mdi-tools')}"></i>
            </span>
            <div class="workflow-selected-template-copy">
              <div class="workflow-selected-template-title">${escapeHtml(specializedDefinition.label)}</div>
              <div class="workflow-selected-template-description">${escapeHtml(specializedDefinition.description)}</div>
            </div>
          </div>
          <div class="stack-sm mt-3">
            ${renderFieldMarkup(specializedDefinition.fields, node)}
          </div>
        `
        : `
          <div class="workflow-empty-copy mt-3">
            Choose a ${node.kind === 'tool' ? 'tool' : 'trigger'} definition to configure its fields.
          </div>
        `
      : '';

    elements.nodeTemplateFields.innerHTML = `
      <div class="stack-sm">
        ${renderFieldMarkup(template.fields, node)}
      </div>
      ${specializedSection}
    `;

    syncRenderedFieldValues(template.fields, node);
    if (specializedDefinition) {
      syncRenderedFieldValues(specializedDefinition.fields, node);
    }
  }

  function renderNodeInspector(): void {
    const selectedNode = getNode(selectedNodeId);
    const template = getNodeTemplate(selectedNode);
    const hasSelectedNode = Boolean(selectedNode);

    elements.nodeEmpty.classList.toggle('d-none', hasSelectedNode);
    elements.nodeFields.classList.toggle('d-none', !hasSelectedNode);

    if (!selectedNode) {
      elements.nodeLabel.value = '';
      elements.nodeKind.value = '';
      elements.selectedTemplate.innerHTML = '';
      elements.nodeTemplateFields.innerHTML = '';
      elements.nodeConfig.value = '';
      return;
    }

    elements.nodeLabel.value = selectedNode.label;
    elements.nodeKind.value = selectedNode.kind;
    renderSelectedTemplate(selectedNode, template);
    renderTemplateFields(selectedNode, template);
    elements.advancedPanel.open = !template;
    syncAdvancedConfigEditor();
  }

  function getQuickAddTemplates(sourceId: string): WorkflowNodeTemplate[] {
    return nodeTemplates
      .filter((template) => !(template.kind === 'trigger' && definition.nodes.length > 0))
      .filter((template) => !(template.kind === getNode(sourceId)?.kind && template.kind === 'trigger'))
      .slice(0, 5);
  }

  function renderQuickAddMenu(sourceId: string): string {
    const items = getQuickAddTemplates(sourceId)
      .map(
        (template) => `
          <button
            type="button"
            class="workflow-node-quick-add-item"
            data-quick-add-kind="${escapeHtml(template.kind)}"
            data-quick-add-source="${escapeHtml(sourceId)}"
          >
            <span class="workflow-node-quick-add-item-icon">
              <i class="mdi ${escapeHtml(template.icon ?? 'mdi-vector-square')}"></i>
            </span>
            <span class="workflow-node-quick-add-item-copy">
              <span class="workflow-node-quick-add-item-title">${escapeHtml(template.label)}</span>
              <span class="workflow-node-quick-add-item-description">${escapeHtml(template.description)}</span>
            </span>
          </button>
        `,
      )
      .join('');

    return `
      <div class="workflow-node-quick-add-menu" data-quick-add-menu="${escapeHtml(sourceId)}">
        <div class="workflow-node-quick-add-header">
          <i class="mdi mdi-magnify"></i>
          <span>Add next step</span>
        </div>
        <div class="workflow-node-quick-add-list">${items}</div>
      </div>
    `;
  }

  function addEdgeBetween(source: string, target: string): boolean {
    if (!source || !target || source === target) {
      return false;
    }

    const duplicate = definition.edges.some((edge) => edge.source === source && edge.target === target);
    if (duplicate) {
      return false;
    }

    definition.edges.push({
      id: createId('edge'),
      source,
      target,
    });
    return true;
  }

  function addConnectedNodeFromKind(sourceId: string, kind: string): void {
    const template = templateMap.get(kind);
    const sourceNode = getNode(sourceId);
    if (!template || !sourceNode) {
      return;
    }

    const siblingCount = definition.edges.filter((edge) => edge.source === sourceId).length;
    const node: WorkflowNode = {
      config: cloneValue(template.config ?? {}),
      id: createId('node'),
      kind: template.kind,
      label: template.label,
      position: {
        x: sourceNode.position.x + NODE_COLUMN_GAP,
        y: sourceNode.position.y + siblingCount * NODE_ROW_GAP * 0.8,
      },
    };

    definition.nodes.push(node);
    addEdgeBetween(sourceId, node.id);
    quickAddSourceId = null;
    connectionDraft = null;
    selectNode(node.id);
  }

  function toggleNodeDisabled(nodeId: string): void {
    const node = getNode(nodeId);
    if (!node) {
      return;
    }

    const nextConfig = { ...(node.config ?? {}) };
    if (nextConfig['disabled']) {
      delete nextConfig['disabled'];
    } else {
      nextConfig['disabled'] = true;
    }
    node.config = nextConfig;
    render();
  }

  function previewRunNode(nodeId: string): void {
    runningNodeId = nodeId;
    render();
    window.setTimeout(() => {
      if (runningNodeId === nodeId) {
        runningNodeId = null;
        render();
      }
    }, 900);
  }

  function beginConnection(sourceId: string, event: MouseEvent | PointerEvent): void {
    quickAddSourceId = null;
    connectionDraft = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      sourceId,
    };
    selectNode(sourceId);
  }

  function completeConnection(targetId: string): void {
    if (!connectionDraft) {
      return;
    }

    const didAdd = addEdgeBetween(connectionDraft.sourceId, targetId);
    connectionDraft = null;
    if (didAdd) {
      selectNode(targetId);
    } else {
      renderEdges();
    }
  }

  function renderEdgeList(): void {
    elements.edgeEmpty.classList.toggle('d-none', definition.edges.length > 0);

    elements.edgeList.innerHTML = definition.edges
      .map((edge) => {
        const source = getNode(edge.source);
        const target = getNode(edge.target);
        const sourceLabel = source ? getNodeTitle(source) : edge.source;
        const targetLabel = target ? getNodeTitle(target) : edge.target;
        return `
          <div class="workflow-edge-item">
            <div class="workflow-edge-copy">
              <span class="workflow-edge-terminal">
                <span class="workflow-edge-terminal-label">Source</span>
                <strong class="workflow-edge-terminal-value">${escapeHtml(sourceLabel)}</strong>
              </span>
              <span class="workflow-edge-arrow" aria-hidden="true">
                <i class="mdi mdi-arrow-right"></i>
              </span>
              <span class="workflow-edge-terminal">
                <span class="workflow-edge-terminal-label">Target</span>
                <strong class="workflow-edge-terminal-value">${escapeHtml(targetLabel)}</strong>
              </span>
            </div>
            <button type="button" class="btn btn-outline-danger btn-sm" data-remove-edge="${escapeHtml(edge.id)}">
              Remove
            </button>
          </div>
        `;
      })
      .join('');
  }

  function renderNodes(): void {
    elements.canvas.innerHTML = '';

    definition.nodes.forEach((node) => {
      const template = getNodeTemplate(node);
      const subtitle = getNodeSubtitle(node, triggerDefinitionMap, toolDefinitionMap);
      const statusLabel = getNodeStatusLabel(node, runningNodeId === node.id);
      const isSelected = node.id === selectedNodeId;
      const nodeElement = document.createElement('article');
      nodeElement.className = [
        'workflow-node',
        `workflow-node--${node.kind}`,
        isSelected ? 'is-selected' : '',
        isNodeDisabled(node) ? 'is-disabled' : '',
        runningNodeId === node.id ? 'is-running' : '',
      ]
        .filter(Boolean)
        .join(' ');
      nodeElement.dataset.nodeId = node.id;
      nodeElement.style.left = `${node.position.x}px`;
      nodeElement.style.top = `${node.position.y}px`;
      nodeElement.innerHTML = `
        <span class="workflow-node-port workflow-node-port--input" data-port-input="${escapeHtml(node.id)}" aria-label="Connect into ${escapeHtml(getNodeTitle(node))}"></span>
        <span class="workflow-node-port workflow-node-port--output" data-port-output="${escapeHtml(node.id)}" aria-label="Connect from ${escapeHtml(getNodeTitle(node))}"></span>
        ${
          isSelected
            ? `
              <div class="workflow-node-toolbar" data-node-toolbar="${escapeHtml(node.id)}">
                <button type="button" class="workflow-node-toolbar-button" data-node-action="run" data-node-action-id="${escapeHtml(node.id)}" aria-label="Run node">
                  <i class="mdi mdi-play"></i>
                </button>
                <button type="button" class="workflow-node-toolbar-button" data-node-action="toggle-disabled" data-node-action-id="${escapeHtml(node.id)}" aria-label="Toggle node state">
                  <i class="mdi ${isNodeDisabled(node) ? 'mdi-power-plug-off-outline' : 'mdi-power'}"></i>
                </button>
                <button type="button" class="workflow-node-toolbar-button" data-node-action="delete" data-node-action-id="${escapeHtml(node.id)}" aria-label="Delete node">
                  <i class="mdi mdi-trash-can-outline"></i>
                </button>
                <button type="button" class="workflow-node-toolbar-button" data-node-action="more" data-node-action-id="${escapeHtml(node.id)}" aria-label="More options">
                  <i class="mdi mdi-dots-horizontal"></i>
                </button>
              </div>
            `
            : ''
        }
        <div class="workflow-node-body" data-node-body="${escapeHtml(node.id)}">
          <div class="workflow-node-accent" aria-hidden="true"></div>
          <div class="workflow-node-header">
            <span class="workflow-node-meta">
              <span class="workflow-node-icon">
                <i class="mdi ${escapeHtml(template?.icon ?? 'mdi-vector-square')}"></i>
              </span>
              <span class="workflow-node-copy">
                <strong class="workflow-node-title">${escapeHtml(getNodeTitle(node))}</strong>
                <span class="workflow-node-subtitle">${escapeHtml(subtitle)}</span>
              </span>
            </span>
            <span class="workflow-node-status">
              <span class="workflow-node-status-dot" aria-hidden="true"></span>
              ${escapeHtml(statusLabel)}
            </span>
          </div>
          <div class="workflow-node-footer">
            <span class="workflow-node-kind">${escapeHtml(formatKindLabel(node.kind))}</span>
            ${
              isSelected
                ? `
                  <button type="button" class="workflow-node-add-next" data-quick-add-toggle="${escapeHtml(node.id)}" aria-label="Add next node">
                    <i class="mdi mdi-plus"></i>
                  </button>
                `
                : ''
            }
          </div>
        </div>
        ${quickAddSourceId === node.id ? renderQuickAddMenu(node.id) : ''}
      `;
      elements.canvas.appendChild(nodeElement);
    });
  }

  function renderEdges(): void {
    const surfaceRect = elements.surface.getBoundingClientRect();
    elements.edgesSvg.setAttribute(
      'viewBox',
      `0 0 ${Math.max(elements.surface.clientWidth, 1)} ${Math.max(elements.surface.clientHeight, 1)}`,
    );
    elements.edgesSvg.innerHTML = '';

    definition.edges.forEach((edge) => {
      const sourceElement = elements.canvas.querySelector<HTMLElement>(`[data-node-id="${edge.source}"]`);
      const targetElement = elements.canvas.querySelector<HTMLElement>(`[data-node-id="${edge.target}"]`);
      if (!sourceElement || !targetElement) {
        return;
      }

      const sourceRect = sourceElement.getBoundingClientRect();
      const targetRect = targetElement.getBoundingClientRect();
      const sourceX = sourceRect.right - surfaceRect.left;
      const sourceY = sourceRect.top - surfaceRect.top + sourceRect.height / 2;
      const targetX = targetRect.left - surfaceRect.left;
      const targetY = targetRect.top - surfaceRect.top + targetRect.height / 2;
      const controlOffset = Math.max(Math.abs(targetX - sourceX) * 0.35, 56);

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute(
        'd',
        `M ${sourceX} ${sourceY} C ${sourceX + controlOffset} ${sourceY}, ${targetX - controlOffset} ${targetY}, ${targetX} ${targetY}`,
      );
      path.setAttribute('class', 'workflow-edge-path');
      elements.edgesSvg.appendChild(path);
    });

    if (connectionDraft) {
      const sourceElement = elements.canvas.querySelector<HTMLElement>(`[data-node-id="${connectionDraft.sourceId}"]`);
      if (!sourceElement) {
        return;
      }

      const sourceRect = sourceElement.getBoundingClientRect();
      const sourceX = sourceRect.right - surfaceRect.left;
      const sourceY = sourceRect.top - surfaceRect.top + sourceRect.height / 2;
      const targetX = connectionDraft.pointerX - surfaceRect.left;
      const targetY = connectionDraft.pointerY - surfaceRect.top;
      const controlOffset = Math.max(Math.abs(targetX - sourceX) * 0.35, 56);
      const draftPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      draftPath.setAttribute(
        'd',
        `M ${sourceX} ${sourceY} C ${sourceX + controlOffset} ${sourceY}, ${targetX - controlOffset} ${targetY}, ${targetX} ${targetY}`,
      );
      draftPath.setAttribute('class', 'workflow-edge-path workflow-edge-path--draft');
      elements.edgesSvg.appendChild(draftPath);
    }
  }

  function render(): void {
    updateSurfaceSize();
    syncDefinition();
    renderNodes();
    renderEdges();
    renderCanvasState();
    renderBoardSummary();
    renderNodeInspector();
    renderEdgeList();
  }

  function selectNode(nodeId: string | null): void {
    selectedNodeId = nodeId;
    render();
  }

  function addNodeFromKind(kind: string): void {
    const template = templateMap.get(kind);
    if (!template) {
      return;
    }

    const index = definition.nodes.length;
    const node: WorkflowNode = {
      config: cloneValue(template.config ?? {}),
      id: createId('node'),
      kind: template.kind,
      label: template.label,
      position: {
        x: 40 + (index % 3) * NODE_COLUMN_GAP,
        y: 40 + Math.floor(index / 3) * NODE_ROW_GAP,
      },
    };

    definition.nodes.push(node);
    quickAddSourceId = null;
    connectionDraft = null;
    selectNode(node.id);
  }

  function updateSelectedNodeKind(kind: string): void {
    const selectedNode = getNode(selectedNodeId);
    const nextTemplate = templateMap.get(kind);
    if (!selectedNode || !nextTemplate) {
      return;
    }

    const previousKind = selectedNode.kind;
    const previousTemplate = getNodeTemplate(selectedNode);
    const authSecretGroupId = getConfigString(selectedNode.config, 'auth_secret_group_id');
    selectedNode.kind = nextTemplate.kind;
    selectedNode.config = cloneValue(nextTemplate.config ?? {});
    if (authSecretGroupId && (nextTemplate.kind === 'tool' || nextTemplate.kind === 'trigger')) {
      selectedNode.config = {
        ...(selectedNode.config ?? {}),
        auth_secret_group_id: authSecretGroupId,
      };
    }
    if (
      !selectedNode.label ||
      selectedNode.label === previousTemplate?.label ||
      selectedNode.label === formatKindLabel(previousKind)
    ) {
      selectedNode.label = nextTemplate.label;
    }
    render();
  }

  function updateSelectedNodeLabel(value: string): void {
    const selectedNode = getNode(selectedNodeId);
    if (!selectedNode) {
      return;
    }

    selectedNode.label = value;
    render();
  }

  function updateSelectedNodeConfig(value: string): void {
    const selectedNode = getNode(selectedNodeId);
    if (!selectedNode) {
      return;
    }

    const trimmedValue = value.trim();
    if (!trimmedValue) {
      selectedNode.config = {};
      elements.nodeConfig.setCustomValidity('');
      syncDefinition();
      return;
    }

    try {
      const parsed = JSON.parse(trimmedValue) as unknown;
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        elements.nodeConfig.setCustomValidity('Runtime config must be a JSON object.');
        elements.nodeConfig.reportValidity();
        return;
      }

      selectedNode.config = parsed as Record<string, unknown>;
      elements.nodeConfig.setCustomValidity('');
      render();
    } catch (error) {
      console.error(error);
      elements.nodeConfig.setCustomValidity('Runtime config must be valid JSON.');
      elements.nodeConfig.reportValidity();
    }
  }

  function updateSelectedTemplateField(fieldKey: string, value: string): void {
    const selectedNode = getNode(selectedNodeId);
    if (!selectedNode) {
      return;
    }

    if (selectedNode.kind === 'trigger' && fieldKey === 'type') {
      const triggerDefinition = triggerDefinitionMap.get(value);
      const authSecretGroupId = getConfigString(selectedNode.config, 'auth_secret_group_id');
      selectedNode.config = {
        ...(authSecretGroupId ? { auth_secret_group_id: authSecretGroupId } : {}),
        ...(triggerDefinition?.config ?? {}),
        type: value || 'manual',
      };
      render();
      return;
    }

    if (selectedNode.kind === 'tool' && fieldKey === 'tool_name') {
      const toolDefinition = toolDefinitionMap.get(value);
      const authSecretGroupId = getConfigString(selectedNode.config, 'auth_secret_group_id');
      selectedNode.config = {
        ...(authSecretGroupId ? { auth_secret_group_id: authSecretGroupId } : {}),
        ...(toolDefinition?.config ?? {}),
        tool_name: value || 'passthrough',
      };
      render();
      return;
    }

    const nextConfig = { ...(selectedNode.config ?? {}) };
    if (selectedNode.kind === 'tool' && !getConfigString(nextConfig, 'tool_name')) {
      nextConfig.tool_name = getToolName(selectedNode.config);
    }
    delete nextConfig.operation;
    if (value === '') {
      delete nextConfig[fieldKey];
    } else {
      nextConfig[fieldKey] = value;
    }

    selectedNode.config = nextConfig;
    syncDefinition();
    syncAdvancedConfigEditor();
  }

  function deleteSelectedNode(): void {
    if (!selectedNodeId) {
      return;
    }

    definition.nodes = definition.nodes.filter((node) => node.id !== selectedNodeId);
    definition.edges = definition.edges.filter(
      (edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId,
    );
    quickAddSourceId = null;
    connectionDraft = null;
    selectedNodeId = definition.nodes[0]?.id ?? null;
    render();
  }

  function removeEdge(edgeId: string): void {
    definition.edges = definition.edges.filter((edge) => edge.id !== edgeId);
    render();
  }

  root.addEventListener('click', (event) => {
    const target = event.target as HTMLElement;

    const templateButton = target.closest<HTMLButtonElement>('[data-add-node]');
    if (templateButton) {
      addNodeFromKind(templateButton.dataset.addNode ?? '');
      return;
    }

    const quickAddButton = target.closest<HTMLButtonElement>('[data-quick-add-kind]');
    if (quickAddButton) {
      addConnectedNodeFromKind(
        quickAddButton.dataset.quickAddSource ?? '',
        quickAddButton.dataset.quickAddKind ?? '',
      );
      return;
    }

    const quickAddToggle = target.closest<HTMLButtonElement>('[data-quick-add-toggle]');
    if (quickAddToggle) {
      const sourceId = quickAddToggle.dataset.quickAddToggle ?? null;
      quickAddSourceId = quickAddSourceId === sourceId ? null : sourceId;
      connectionDraft = null;
      render();
      return;
    }

    const nodeActionButton = target.closest<HTMLButtonElement>('[data-node-action]');
    if (nodeActionButton) {
      const action = nodeActionButton.dataset.nodeAction ?? '';
      const nodeId = nodeActionButton.dataset.nodeActionId ?? '';
      if (action === 'run') {
        previewRunNode(nodeId);
      } else if (action === 'toggle-disabled') {
        toggleNodeDisabled(nodeId);
      } else if (action === 'delete') {
        if (nodeId === selectedNodeId) {
          deleteSelectedNode();
        } else {
          selectNode(nodeId);
          deleteSelectedNode();
        }
      } else if (action === 'more') {
        quickAddSourceId = quickAddSourceId === nodeId ? null : nodeId;
        connectionDraft = null;
        render();
      }
      return;
    }

    const outputPort = target.closest<HTMLElement>('[data-port-output]');
    if (outputPort) {
      beginConnection(outputPort.dataset.portOutput ?? '', event as MouseEvent);
      return;
    }

    const inputPort = target.closest<HTMLElement>('[data-port-input]');
    if (inputPort) {
      completeConnection(inputPort.dataset.portInput ?? '');
      return;
    }

    const nodeElement = target.closest<HTMLElement>('[data-node-id]');
    if (nodeElement) {
      const nodeId = nodeElement.dataset.nodeId ?? null;
      if (connectionDraft && nodeId && connectionDraft.sourceId !== nodeId) {
        completeConnection(nodeId);
      } else {
        quickAddSourceId = null;
        selectNode(nodeId);
      }
      return;
    }

    const removeEdgeButton = target.closest<HTMLButtonElement>('[data-remove-edge]');
    if (removeEdgeButton) {
      removeEdge(removeEdgeButton.dataset.removeEdge ?? '');
      return;
    }

    if (!target.closest('[data-node-palette]')) {
      quickAddSourceId = null;
      connectionDraft = null;
      render();
    }
  });

  elements.canvas.addEventListener('pointerdown', (event) => {
    const nodeElement = (event.target as HTMLElement).closest<HTMLElement>('[data-node-id]');
    if (!nodeElement) {
      return;
    }

    if (
      (event.target as HTMLElement).closest(
        '[data-port-input], [data-port-output], [data-node-action], [data-quick-add-toggle], [data-quick-add-menu]',
      )
    ) {
      return;
    }

    const nodeId = nodeElement.dataset.nodeId ?? null;
    if (!nodeId) {
      return;
    }

    selectNode(nodeId);
    const node = getNode(nodeId);
    if (!node) {
      return;
    }

    const surfaceRect = elements.surface.getBoundingClientRect();
    dragState = {
      id: nodeId,
      offsetX: event.clientX - surfaceRect.left - node.position.x,
      offsetY: event.clientY - surfaceRect.top - node.position.y,
    };
    nodeElement.setPointerCapture(event.pointerId);
  });

  window.addEventListener('pointermove', (event) => {
    if (!dragState) {
      if (connectionDraft) {
        connectionDraft.pointerX = event.clientX;
        connectionDraft.pointerY = event.clientY;
        renderEdges();
      }
      return;
    }

    const draggedNode = getNode(dragState.id);
    if (!draggedNode) {
      dragState = null;
      return;
    }

    const surfaceRect = elements.surface.getBoundingClientRect();
    draggedNode.position.x = clamp(
      event.clientX - surfaceRect.left - dragState.offsetX,
      0,
      Math.max(elements.surface.clientWidth - NODE_WIDTH, 0),
    );
    draggedNode.position.y = clamp(
      event.clientY - surfaceRect.top - dragState.offsetY,
      0,
      Math.max(elements.surface.clientHeight - NODE_HEIGHT, 0),
    );
    render();
  });

  window.addEventListener('pointerup', () => {
    dragState = null;
  });

  elements.nodeLabel.addEventListener('input', () => {
    updateSelectedNodeLabel(elements.nodeLabel.value);
  });
  elements.nodeKind.addEventListener('change', () => {
    updateSelectedNodeKind(elements.nodeKind.value);
  });

  elements.nodeTemplateFields.addEventListener('input', (event) => {
    const field = (event.target as HTMLElement).closest<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >('[data-config-field]');
    if (!field) {
      return;
    }

    updateSelectedTemplateField(field.dataset.configField ?? '', field.value);
  });

  elements.nodeTemplateFields.addEventListener('change', (event) => {
    const field = (event.target as HTMLElement).closest<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >('[data-config-field]');
    if (!field) {
      return;
    }

    updateSelectedTemplateField(field.dataset.configField ?? '', field.value);
  });

  elements.nodeConfig.addEventListener('change', () => {
    updateSelectedNodeConfig(elements.nodeConfig.value);
  });
  elements.deleteNodeButton.addEventListener('click', deleteSelectedNode);
  root.addEventListener('submit', syncDefinition);

  render();
}

export { initWorkflowDesigner };
