import type { CanvasElements } from '../dom';
import type {
  WorkflowNode,
  WorkflowNodeDefinition,
  WorkflowNodeTemplateField,
} from '../types';
import {
  buildTemplateInsertionValue,
  getNodeSettingControl,
} from './settingsAssist';
import {
  getRuntimeTemplateFieldInputModeDefault,
  getTemplateFieldInputMode,
  supportsTemplateFieldInputMode,
  WORKFLOW_NODE_INPUT_MODES_KEY,
} from '../utils';

type SettingsFieldSelection = {
  field: WorkflowNodeTemplateField;
  node: WorkflowNode;
};

type SettingsControllerParams = {
  canvas: Pick<CanvasElements, 'settingsFields' | 'settingsTitle'>;
  getNode: (nodeId: string | null | undefined) => WorkflowNode | undefined;
  getNodeDefinition: (node: WorkflowNode | undefined) => WorkflowNodeDefinition | undefined;
  getSettingsNodeId: () => string | null;
  renderCanvas: () => void;
  renderSettingsPanel: () => void;
  syncDefinitionInput: () => void;
  syncNodeTargetEdges: (node: WorkflowNode, nodeDefinition: WorkflowNodeDefinition | undefined) => void;
};

export function createWorkflowDesignerSettingsController(params: SettingsControllerParams): {
  applyNodeSettingSuggestion: (key: string, value: string, binding: 'literal' | 'path' | 'template') => void;
  updateSelectedNodeField: (
    key: string,
    value: string,
    options?: { rerenderSettings?: boolean },
  ) => void;
  updateSelectedNodeFieldMode: (
    key: string,
    mode: 'expression' | 'static',
    options?: { rerenderSettings?: boolean },
  ) => void;
  updateSelectedNodeLabel: (value: string, options?: { rerenderSettings?: boolean }) => void;
} {
  const {
    canvas,
    getNode,
    getNodeDefinition,
    getSettingsNodeId,
    renderCanvas,
    renderSettingsPanel,
    syncDefinitionInput,
    syncNodeTargetEdges,
  } = params;

  function getSelectedSettingsField(key: string): SettingsFieldSelection | null {
    const settingsNode = getNode(getSettingsNodeId());
    const nodeDefinition = getNodeDefinition(settingsNode);
    if (!settingsNode || !nodeDefinition) {
      return null;
    }

    const field = nodeDefinition.fields.find((item) => item.key === key);
    if (!field) {
      return null;
    }

    return { field, node: settingsNode };
  }

  function updateSelectedNodeFieldMode(
    key: string,
    mode: 'expression' | 'static',
    options?: { rerenderSettings?: boolean },
  ): void {
    const fieldSelection = getSelectedSettingsField(key);
    if (!fieldSelection || !supportsTemplateFieldInputMode(fieldSelection.field)) {
      return;
    }

    const { field, node } = fieldSelection;
    const nextConfig = { ...(node.config ?? {}) };
    const currentModesValue = nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
    const nextModes =
      currentModesValue && typeof currentModesValue === 'object' && !Array.isArray(currentModesValue)
        ? { ...(currentModesValue as Record<string, unknown>) }
        : {};
    const defaultMode = getRuntimeTemplateFieldInputModeDefault(field);

    if (mode === defaultMode) {
      delete nextModes[key];
    } else {
      nextModes[key] = mode;
    }

    if (Object.keys(nextModes).length > 0) {
      nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY] = nextModes;
    } else {
      delete nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
    }

    node.config = nextConfig;
    syncDefinitionInput();
    renderCanvas();
    if (options?.rerenderSettings) {
      renderSettingsPanel();
    }
  }

  function updateSelectedNodeLabel(value: string, options?: { rerenderSettings?: boolean }): void {
    const settingsNode = getNode(getSettingsNodeId());
    if (!settingsNode) {
      return;
    }

    settingsNode.label = value;
    syncDefinitionInput();
    renderCanvas();
    if (options?.rerenderSettings) {
      renderSettingsPanel();
      return;
    }

    canvas.settingsTitle.textContent = value || getNodeDefinition(settingsNode)?.label || settingsNode.type;
  }

  function updateSelectedNodeField(
    key: string,
    value: string,
    options?: { rerenderSettings?: boolean },
  ): void {
    const settingsNode = getNode(getSettingsNodeId());
    const nodeDefinition = getNodeDefinition(settingsNode);
    if (!settingsNode || !nodeDefinition) {
      return;
    }

    const nextConfig = { ...(settingsNode.config ?? {}) };
    if (value === '') {
      delete nextConfig[key];
    } else {
      nextConfig[key] = value;
    }

    const field = nodeDefinition.fields.find((item) => item.key === key);
    if (field && supportsTemplateFieldInputMode(field)) {
      const currentModesValue = nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
      const nextModes =
        currentModesValue && typeof currentModesValue === 'object' && !Array.isArray(currentModesValue)
          ? { ...(currentModesValue as Record<string, unknown>) }
          : {};
      if (value === '') {
        delete nextModes[key];
      } else {
        const runtimeDefaultMode = getRuntimeTemplateFieldInputModeDefault(field);
        const selectedMode = getTemplateFieldInputMode(settingsNode, field);

        if (selectedMode === runtimeDefaultMode) {
          delete nextModes[key];
        } else {
          nextModes[key] = selectedMode;
        }
      }

      if (Object.keys(nextModes).length > 0) {
        nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY] = nextModes;
      } else {
        delete nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
      }
    }

    settingsNode.config = nextConfig;

    syncNodeTargetEdges(settingsNode, getNodeDefinition(settingsNode));
    syncDefinitionInput();
    renderCanvas();
    if (options?.rerenderSettings) {
      renderSettingsPanel();
    }
  }

  function applyNodeSettingSuggestion(
    key: string,
    value: string,
    binding: 'literal' | 'path' | 'template',
  ): void {
    const control = getNodeSettingControl(canvas.settingsFields, key);
    if (!control) {
      return;
    }

    const fieldSelection = getSelectedSettingsField(key);
    if (fieldSelection && supportsTemplateFieldInputMode(fieldSelection.field) && binding === 'template') {
      updateSelectedNodeFieldMode(key, 'expression');
    }

    const nextValue = binding === 'template' && (control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement)
      ? buildTemplateInsertionValue(control, value)
      : value;

    control.value = nextValue;
    updateSelectedNodeField(key, nextValue, { rerenderSettings: true });
  }

  return {
    applyNodeSettingSuggestion,
    updateSelectedNodeField,
    updateSelectedNodeFieldMode,
    updateSelectedNodeLabel,
  };
}
