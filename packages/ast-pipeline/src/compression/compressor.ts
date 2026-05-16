import { ExtractedAST } from '../parser/types';
import { CompressedNode, NodeType } from '../validation/schema';
import { generateDeterministicId } from './ids';
import { estimateTokens } from './tokenizer';
import * as t from '@babel/types';

export function compressAST(extracted: ExtractedAST): Record<string, CompressedNode> {
  const nodes: Record<string, CompressedNode> = {};

  const addNode = (node: CompressedNode) => {
    // Calculate token budget before adding
    const nodeJson = JSON.stringify(node);
    const tokens = estimateTokens(nodeJson);
    node.metrics = { tokens };
    nodes[node.id] = node;
  };

  const transformLoc = (loc?: t.SourceLocation | null) => {
    if (!loc) return undefined;
    return {
      start: { line: loc.start.line, column: loc.start.column },
      end: { line: loc.end.line, column: loc.end.column }
    };
  };

  // Add Imports
  extracted.imports.forEach(imp => {
    const id = generateDeterministicId('Import', imp.source, imp.loc?.start.line || 0);
    addNode({
      id,
      type: 'Import',
      name: imp.source,
      value: imp.specifiers.join(','),
      children: [],
      loc: transformLoc(imp.loc)
    });
  });

  // Add Exports
  extracted.exports.forEach(exp => {
    const id = generateDeterministicId('Export', exp.name, exp.loc?.start.line || 0);
    addNode({
      id,
      type: 'Export',
      name: exp.name,
      value: exp.isDefault ? 'default' : 'named',
      children: [],
      loc: transformLoc(exp.loc)
    });
  });

  // Add Components
  extracted.components.forEach(comp => {
    const compId = generateDeterministicId('Component', comp.name, comp.loc?.start.line || 0);
    const childrenIds: string[] = [];

    // Props
    comp.props.forEach(prop => {
      const propId = generateDeterministicId('Prop', comp.name, prop);
      addNode({
        id: propId,
        type: 'Prop',
        name: prop,
        children: []
      });
      childrenIds.push(propId);
    });

    // Hooks
    comp.hooks.forEach((hook, i) => {
      const hookId = generateDeterministicId('Hook', comp.name, hook.name, i);
      addNode({
        id: hookId,
        type: 'Hook',
        name: hook.name,
        children: [],
        loc: transformLoc(hook.loc)
      });
      childrenIds.push(hookId);
    });

    // States
    comp.states.forEach(state => {
      const stateId = generateDeterministicId('State', comp.name, state.name);
      addNode({
        id: stateId,
        type: 'State',
        name: state.name,
        value: state.setter,
        children: [],
        loc: transformLoc(state.loc)
      });
      childrenIds.push(stateId);
    });

    // Effects
    comp.effects.forEach((effect, i) => {
      const effectId = generateDeterministicId('Effect', comp.name, i);
      addNode({
        id: effectId,
        type: 'Effect',
        value: (effect.dependencies || []).join(','),
        children: [],
        loc: transformLoc(effect.loc)
      });
      childrenIds.push(effectId);
    });

    // JSX
    comp.jsxElements.forEach((jsx, i) => {
      const jsxId = generateDeterministicId('JSX', comp.name, jsx.name, i);
      addNode({
        id: jsxId,
        type: 'JSX',
        name: jsx.name,
        value: jsx.props.join(','),
        children: [],
        loc: transformLoc(jsx.loc)
      });
      childrenIds.push(jsxId);
    });
    
    // Function Calls inside component
    comp.functionCalls.forEach((call, i) => {
      const callId = generateDeterministicId('Function', comp.name, call.name, i);
      addNode({
        id: callId,
        type: 'Function',
        name: call.name,
        children: [],
        loc: transformLoc(call.loc)
      });
      childrenIds.push(callId);
    });

    addNode({
      id: compId,
      type: 'Component',
      name: comp.name,
      children: childrenIds,
      loc: transformLoc(comp.loc)
    });
  });

  return nodes;
}
