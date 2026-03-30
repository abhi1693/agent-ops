import type { DesignerElements } from './types';

export function getDesignerElements(root: ParentNode): DesignerElements | null {
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
    return null;
  }

  return {
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
}
