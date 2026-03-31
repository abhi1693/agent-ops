import {
  DEFAULT_SURFACE_HEIGHT,
  NODE_COLUMN_GAP,
  NODE_HEIGHT,
  NODE_ROW_GAP,
  NODE_WIDTH,
  SURFACE_PADDING,
} from './workflowDesigner/constants';
import { getDesignerElements } from './workflowDesigner/dom';
import {
  renderEdgeListMarkup,
  renderNodeMarkup,
  renderNodePaletteMarkup,
  renderQuickAddMenuMarkup,
  renderSelectedTemplateMarkup,
  renderTemplateFieldsMarkup,
} from './workflowDesigner/markup';
import {
  buildNodeRegistry,
  getAvailablePaletteSections,
  getNodeDefinition,
} from './workflowDesigner/registry/nodeRegistry';
import {
  normalizeWorkflowDefinition,
  serializeWorkflowDefinition,
} from './workflowDesigner/schema/workflowSchema';
import type {
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeTemplate,
  WorkflowNodeTemplateField,
  WorkflowPersistedDefinition,
} from './workflowDesigner/types';
import {
  clamp,
  cloneValue,
  createId,
  formatCount,
  formatKindLabel,
  getConfigString,
  getNodeStatusLabel,
  getNodeSubtitle,
  getTemplateFieldOptions,
  getNodeTitle,
  getTemplateFieldValue,
  isNodeDisabled,
  parseJsonScript,
} from './workflowDesigner/utils';

function initWorkflowDesigner(): void {
  const root = document.querySelector<HTMLElement>('[data-workflow-designer]');
  if (!root) {
    return;
  }

  const resolvedElements = getDesignerElements(root);
  if (!resolvedElements) {
    return;
  }
  const elements = resolvedElements;

  const definition = normalizeWorkflowDefinition(
    parseJsonScript<WorkflowPersistedDefinition>('workflow-definition-data', { nodes: [], edges: [] }),
  );
  const nodeTemplates = parseJsonScript<WorkflowNodeTemplate[]>('workflow-node-templates-data', []);
  const nodeRegistry = buildNodeRegistry(nodeTemplates);

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
    elements.definitionInput.value = JSON.stringify(serializeWorkflowDefinition(definition));
  }

  function getNode(nodeId: string | null): WorkflowNode | undefined {
    if (!nodeId) {
      return undefined;
    }

    return definition.nodes.find((node) => node.id === nodeId);
  }

  function getNodeTemplate(node: WorkflowNode | undefined): WorkflowNodeDefinition | undefined {
    return getNodeDefinition(nodeRegistry, node);
  }

  function updateSurfaceSize(): void {
    const maxX = definition.nodes.reduce(
      (value, node) => Math.max(value, node.position.x + NODE_WIDTH),
      0,
    );
    const maxY = definition.nodes.reduce(
      (value, node) => Math.max(value, node.position.y + NODE_HEIGHT),
      0,
    );
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

  function renderNodePalette(): void {
    elements.nodePalette.innerHTML = renderNodePaletteMarkup(
      getAvailablePaletteSections(nodeRegistry, definition),
    );
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

  function syncRenderedFieldValues(
    fields: WorkflowNodeTemplateField[],
    node: WorkflowNode,
  ): void {
    fields.forEach((field) => {
      if (field.type !== 'node_target') {
        return;
      }

      const targetSelect = elements.nodeTemplateFields.querySelector<HTMLSelectElement>(
        `[data-config-field="${field.key}"]`,
      );
      if (targetSelect) {
        targetSelect.value = getTemplateFieldValue(node, field);
      }
    });
  }

  function synchronizeTemplateDrivenConfig(
    node: WorkflowNode,
    template: WorkflowNodeDefinition,
  ): void {
    const nextConfig = { ...(node.config ?? {}) };
    let didChange = false;

    template.fields.forEach((field) => {
      if (field.type !== 'select' || !field.options_by_field) {
        return;
      }

      const options = getTemplateFieldOptions({ ...node, config: nextConfig }, field);
      if (!options.length) {
        return;
      }

      const currentValue =
        typeof nextConfig[field.key] === 'string' ? String(nextConfig[field.key]) : '';
      const optionValues = options.map((option) => option.value);
      if (!currentValue || !optionValues.includes(currentValue)) {
        nextConfig[field.key] = options[0]?.value ?? '';
        didChange = true;
      }
    });

    if (didChange) {
      node.config = nextConfig;
    }
  }

  function synchronizeTemplateConfigs(): void {
    definition.nodes.forEach((node) => {
      const template = getNodeTemplate(node);
      if (!template) {
        return;
      }
      synchronizeTemplateDrivenConfig(node, template);
    });
  }

  function renderTemplateFields(
    node: WorkflowNode | undefined,
    template: WorkflowNodeDefinition | undefined,
  ): void {
    if (!node || !template) {
      elements.nodeTemplateFields.innerHTML = '';
      return;
    }

    elements.nodeTemplateFields.innerHTML = renderTemplateFieldsMarkup({
      node,
      nodes: definition.nodes,
      template,
    });

    syncRenderedFieldValues(template.fields, node);
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
    elements.nodeKind.value = selectedNode.type;
    elements.selectedTemplate.innerHTML = renderSelectedTemplateMarkup(selectedNode, template);
    renderTemplateFields(selectedNode, template);
    elements.advancedPanel.open = !template;
    syncAdvancedConfigEditor();
  }

  function getQuickAddTemplates(_sourceId: string): WorkflowNodeDefinition[] {
    return nodeRegistry.definitions
      .filter((definitionItem) => !(definitionItem.kind === 'trigger' && definition.nodes.length > 0))
      .slice(0, 5);
  }

  function createNodeFromDefinition(
    definitionItem: WorkflowNodeDefinition,
    position: { x: number; y: number },
  ): WorkflowNode {
    return {
      config: cloneValue(definitionItem.config ?? {}),
      id: createId('node'),
      kind: definitionItem.kind,
      label: definitionItem.label,
      position,
      type: definitionItem.type,
      typeVersion: definitionItem.typeVersion,
    };
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
    const template = nodeRegistry.definitionMap.get(kind);
    const sourceNode = getNode(sourceId);
    if (!template || !sourceNode) {
      return;
    }

    const siblingCount = definition.edges.filter((edge) => edge.source === sourceId).length;
    const node = createNodeFromDefinition(template, {
        x: sourceNode.position.x + NODE_COLUMN_GAP,
        y: sourceNode.position.y + siblingCount * NODE_ROW_GAP * 0.8,
      });

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
    elements.edgeList.innerHTML = renderEdgeListMarkup({
      edges: definition.edges,
      getNodeById: getNode,
    });
  }

  function renderNodes(): void {
    elements.canvas.innerHTML = '';

    definition.nodes.forEach((node) => {
      const template = getNodeTemplate(node);
      const subtitle = getNodeSubtitle(node, template);
      const statusLabel = getNodeStatusLabel(node, runningNodeId === node.id);
      const isSelected = node.id === selectedNodeId;
      const isDisabled = isNodeDisabled(node);
      const isRunning = runningNodeId === node.id;
      const showQuickAddMenu = quickAddSourceId === node.id;
      const nodeElement = document.createElement('article');

      nodeElement.className = [
        'workflow-node',
        `workflow-node--${node.kind}`,
        isSelected ? 'is-selected' : '',
        isDisabled ? 'is-disabled' : '',
        isRunning ? 'is-running' : '',
      ]
        .filter(Boolean)
        .join(' ');
      nodeElement.dataset.nodeId = node.id;
      nodeElement.style.left = `${node.position.x}px`;
      nodeElement.style.top = `${node.position.y}px`;
      nodeElement.innerHTML = renderNodeMarkup({
        isDisabled,
        isRunning,
        isSelected,
        node,
        quickAddMenuMarkup: showQuickAddMenu
          ? renderQuickAddMenuMarkup(node.id, getQuickAddTemplates(node.id))
          : '',
        showQuickAddMenu,
        statusLabel,
        subtitle,
        template,
      });
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
      const sourceElement = elements.canvas.querySelector<HTMLElement>(
        `[data-node-id="${connectionDraft.sourceId}"]`,
      );
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
    synchronizeTemplateConfigs();
    updateSurfaceSize();
    syncDefinition();
    renderNodePalette();
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
    const template = nodeRegistry.definitionMap.get(kind);
    if (!template) {
      return;
    }

    if (template.kind === 'trigger' && definition.nodes.some((node) => node.kind === 'trigger')) {
      return;
    }

    const index = definition.nodes.length;
    const node = createNodeFromDefinition(template, {
        x: 40 + (index % 3) * NODE_COLUMN_GAP,
        y: 40 + Math.floor(index / 3) * NODE_ROW_GAP,
      });

    definition.nodes.push(node);
    quickAddSourceId = null;
    connectionDraft = null;
    selectNode(node.id);
  }

  function updateSelectedNodeKind(kind: string): void {
    const selectedNode = getNode(selectedNodeId);
    const nextTemplate = nodeRegistry.definitionMap.get(kind);
    if (!selectedNode || !nextTemplate) {
      return;
    }

    if (
      nextTemplate.kind === 'trigger' &&
      definition.nodes.some((node) => node.id !== selectedNode.id && node.kind === 'trigger')
    ) {
      return;
    }

    const previousKind = selectedNode.kind;
    const previousTemplate = getNodeTemplate(selectedNode);
    const authSecretGroupId = getConfigString(selectedNode.config, 'auth_secret_group_id');
    const supportsAuthSecretGroup = nextTemplate.fields.some(
      (field) => field.key === 'auth_secret_group_id',
    );
    selectedNode.type = nextTemplate.type;
    selectedNode.typeVersion = nextTemplate.typeVersion;
    selectedNode.kind = nextTemplate.kind;
    selectedNode.config = cloneValue(nextTemplate.config ?? {});
    if (authSecretGroupId && supportsAuthSecretGroup) {
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

  function updateSelectedTemplateField(fieldKey: string, value: string, rerender = false): void {
    const selectedNode = getNode(selectedNodeId);
    if (!selectedNode) {
      return;
    }

    const nextConfig = { ...(selectedNode.config ?? {}) };
    if (value === '') {
      delete nextConfig[fieldKey];
    } else {
      nextConfig[fieldKey] = value;
    }

    selectedNode.config = nextConfig;
    if (rerender) {
      render();
      return;
    }

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

    updateSelectedTemplateField(field.dataset.configField ?? '', field.value, true);
  });

  elements.nodeConfig.addEventListener('change', () => {
    updateSelectedNodeConfig(elements.nodeConfig.value);
  });
  elements.deleteNodeButton.addEventListener('click', deleteSelectedNode);
  root.addEventListener('submit', syncDefinition);

  render();
}

export { initWorkflowDesigner };
