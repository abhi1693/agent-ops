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
  normalizeFieldInputValue,
  setConfigValueAtPath,
  getTemplateFieldInputMode,
  supportsTemplateFieldInputMode,
  WORKFLOW_NODE_INPUT_MODES_KEY,
} from '../utils';

type SettingsFieldSelection = {
  field: WorkflowNodeTemplateField;
  node: WorkflowNode;
};

type SettingsFieldInputMetadata = Pick<WorkflowNodeTemplateField, 'type' | 'value_type'>;

function buildCollectionItemDefaults(fields: WorkflowNodeTemplateField[]): Record<string, unknown> {
  return fields.reduce<Record<string, unknown>>((accumulator, field) => {
    if (field.default !== undefined) {
      accumulator[field.key] = field.default;
    }
    return accumulator;
  }, {});
}

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
  addSelectedNodeCollectionItem: (fieldKey: string, optionKey: string) => void;
  applyNodeSettingSuggestion: (key: string, value: string, binding: 'literal' | 'path' | 'template') => void;
  removeSelectedNodeCollectionItem: (fieldKey: string, optionKey: string, itemIndex: number) => void;
  updateSelectedNodeField: (
    key: string,
    value: string,
    options?: { rerenderSettings?: boolean },
  ) => void;
  updateSelectedNodeFieldPath: (
    path: string,
    value: string,
    field: SettingsFieldInputMetadata,
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

  function addSelectedNodeCollectionItem(fieldKey: string, optionKey: string): void {
    const settingsNode = getNode(getSettingsNodeId());
    const nodeDefinition = getNodeDefinition(settingsNode);
    if (!settingsNode || !nodeDefinition) {
      return;
    }

    const nextConfig = { ...(settingsNode.config ?? {}) };
    const currentValue = nextConfig[fieldKey];
    const nextFieldValue =
      currentValue && typeof currentValue === 'object' && !Array.isArray(currentValue)
        ? { ...(currentValue as Record<string, unknown>) }
        : {};
    const currentItems = nextFieldValue[optionKey];
    const nextItems = Array.isArray(currentItems) ? [...currentItems] : [];
    const fieldDefinition = nodeDefinition.fields.find((field) => field.key === fieldKey);
    const collectionOption = fieldDefinition?.collection_options?.find((option) => option.key === optionKey);
    nextItems.push(collectionOption ? buildCollectionItemDefaults(collectionOption.fields) : {});
    nextFieldValue[optionKey] = nextItems;
    nextConfig[fieldKey] = nextFieldValue;
    settingsNode.config = nextConfig;
    syncDefinitionInput();
    renderCanvas();
    renderSettingsPanel();
  }

  function removeSelectedNodeCollectionItem(fieldKey: string, optionKey: string, itemIndex: number): void {
    const settingsNode = getNode(getSettingsNodeId());
    if (!settingsNode) {
      return;
    }

    const nextConfig = { ...(settingsNode.config ?? {}) };
    const currentValue = nextConfig[fieldKey];
    if (!currentValue || typeof currentValue !== 'object' || Array.isArray(currentValue)) {
      return;
    }

    const nextFieldValue = { ...(currentValue as Record<string, unknown>) };
    const currentItems = nextFieldValue[optionKey];
    if (!Array.isArray(currentItems)) {
      return;
    }

    const nextItems = [...currentItems];
    nextItems.splice(itemIndex, 1);
    if (nextItems.length > 0) {
      nextFieldValue[optionKey] = nextItems;
    } else {
      delete nextFieldValue[optionKey];
    }

    if (Object.keys(nextFieldValue).length > 0) {
      nextConfig[fieldKey] = nextFieldValue;
    } else {
      delete nextConfig[fieldKey];
    }

    settingsNode.config = nextConfig;
    syncDefinitionInput();
    renderCanvas();
    renderSettingsPanel();
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
    const field = nodeDefinition.fields.find((item) => item.key === key);
    const normalizedValue = field
      ? normalizeFieldInputValue(field, value)
      : value === ''
        ? undefined
        : value;

    if (normalizedValue === undefined) {
      delete nextConfig[key];
    } else {
      nextConfig[key] = normalizedValue;
    }

    if (field && supportsTemplateFieldInputMode(field)) {
      const currentModesValue = nextConfig[WORKFLOW_NODE_INPUT_MODES_KEY];
      const nextModes =
        currentModesValue && typeof currentModesValue === 'object' && !Array.isArray(currentModesValue)
          ? { ...(currentModesValue as Record<string, unknown>) }
          : {};
      if (normalizedValue === undefined) {
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

  function updateSelectedNodeFieldPath(
    path: string,
    value: string,
    field: SettingsFieldInputMetadata,
    options?: { rerenderSettings?: boolean },
  ): void {
    const settingsNode = getNode(getSettingsNodeId());
    if (!settingsNode) {
      return;
    }

    settingsNode.config = setConfigValueAtPath(
      { ...(settingsNode.config ?? {}) },
      path,
      normalizeFieldInputValue(field, value),
    );

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
    addSelectedNodeCollectionItem,
    applyNodeSettingSuggestion,
    removeSelectedNodeCollectionItem,
    updateSelectedNodeField,
    updateSelectedNodeFieldPath,
    updateSelectedNodeFieldMode,
    updateSelectedNodeLabel,
  };
}
