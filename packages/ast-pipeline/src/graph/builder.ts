import { CompressedNode, DependencyGraph, GraphEdge } from './types';

export function buildGraph(nodes: Record<string, CompressedNode>): DependencyGraph {
  const edges: GraphEdge[] = [];
  let totalTokens = 0;

  const nodesList = Object.values(nodes);
  
  // Build lookup maps
  const componentNames = new Set(nodesList.filter(n => n.type === 'Component').map(n => n.name));

  nodesList.forEach(node => {
    totalTokens += node.metrics?.tokens || 0;

    // 1. Contains edges (Parent -> Child)
    node.children.forEach(childId => {
      edges.push({ source: node.id, target: childId, type: 'contains' });
    });

    // 2. Component specific relationships
    if (node.type === 'Component') {
      node.children.forEach(childId => {
        const child = nodes[childId];
        if (child) {
          if (child.type === 'Hook') {
            edges.push({ source: node.id, target: childId, type: 'uses_hook' });
          } else if (child.type === 'JSX') {
            // Check if JSX renders another component
            if (child.name && componentNames.has(child.name)) {
              // Find the target component node
              const targetComp = nodesList.find(n => n.type === 'Component' && n.name === child.name);
              if (targetComp) {
                edges.push({ source: node.id, target: targetComp.id, type: 'renders' });
              }
            }
          } else if (child.type === 'Prop') {
            edges.push({ source: node.id, target: childId, type: 'has_prop' });
          } else if (child.type === 'Function') {
            edges.push({ source: node.id, target: childId, type: 'calls' });
          }
        }
      });
    }
  });

  return { nodes, edges, metrics: { totalTokens } };
}
