import { z } from 'zod';

export const LocationSchema = z.object({
  start: z.object({ line: z.number(), column: z.number() }),
  end: z.object({ line: z.number(), column: z.number() })
});

export const NodeTypeSchema = z.enum([
  'File',
  'Import',
  'Export',
  'Component',
  'Hook',
  'Function',
  'State',
  'Effect',
  'JSX',
  'Prop'
]);

export const CompressedNodeSchema = z.object({
  id: z.string(),
  type: NodeTypeSchema,
  name: z.string().optional(),
  value: z.string().optional(),
  children: z.array(z.string()),
  loc: LocationSchema.optional(),
  metrics: z.object({
    tokens: z.number()
  }).optional()
});

export const EdgeTypeSchema = z.enum([
  'imports',
  'calls',
  'uses_hook',
  'renders',
  'has_prop',
  'contains',
  'depends_on'
]);

export const GraphEdgeSchema = z.object({
  source: z.string(),
  target: z.string(),
  type: EdgeTypeSchema
});

export const DependencyGraphSchema = z.object({
  nodes: z.record(z.string(), CompressedNodeSchema),
  edges: z.array(GraphEdgeSchema),
  metrics: z.object({
    totalTokens: z.number()
  })
});

export type Location = z.infer<typeof LocationSchema>;
export type NodeType = z.infer<typeof NodeTypeSchema>;
export type CompressedNode = z.infer<typeof CompressedNodeSchema>;
export type EdgeType = z.infer<typeof EdgeTypeSchema>;
export type GraphEdge = z.infer<typeof GraphEdgeSchema>;
export type DependencyGraph = z.infer<typeof DependencyGraphSchema>;
