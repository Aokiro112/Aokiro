import * as fs from 'fs';
import * as path from 'path';
import {
  parseFile,
  extractASTInfo,
  compressAST,
  buildGraph,
  DependencyGraphSchema,
  freeTokenizer
} from '../src';

describe('AST Pipeline Phase A', () => {
  let code: string;

  beforeAll(() => {
    code = fs.readFileSync(path.join(__dirname, '__fixtures__', 'example.tsx'), 'utf-8');
  });

  afterAll(() => {
    freeTokenizer();
  });

  it('should parse and extract AST info successfully', () => {
    const ast = parseFile(code);
    const extracted = extractASTInfo(ast);
    
    expect(extracted.imports.length).toBeGreaterThan(0);
    expect(extracted.components.length).toBe(1);
    
    const comp = extracted.components[0];
    expect(comp.name).toBe('ExampleComponent');
    expect(comp.props).toContain('title');
    expect(comp.hooks.map(h => h.name)).toContain('useAuth');
    expect(comp.states.map(s => s.name)).toContain('count');
    expect(comp.effects.length).toBe(1);
    expect(comp.jsxElements.map(j => j.name)).toContain('Button');
  });

  it('should compress AST into deterministic JSON', () => {
    const ast = parseFile(code);
    const extracted = extractASTInfo(ast);
    const compressed = compressAST(extracted);
    
    const nodes = Object.values(compressed);
    expect(nodes.length).toBeGreaterThan(0);
    
    // Check tokens are calculated
    const compNode = nodes.find(n => n.type === 'Component' && n.name === 'ExampleComponent');
    expect(compNode).toBeDefined();
    expect(compNode?.metrics?.tokens).toBeGreaterThan(0);
  });

  it('should build a valid dependency graph', () => {
    const ast = parseFile(code);
    const extracted = extractASTInfo(ast);
    const compressed = compressAST(extracted);
    const graph = buildGraph(compressed);
    
    // Validate schema
    const result = DependencyGraphSchema.safeParse(graph);
    expect(result.success).toBe(true);

    expect(graph.metrics.totalTokens).toBeGreaterThan(0);
    
    // Check edges
    const usesHookEdges = graph.edges.filter(e => e.type === 'uses_hook');
    expect(usesHookEdges.length).toBeGreaterThan(0);
    
    // Ensure that renders edge doesn't throw or works if components exist
    // Button is not a parsed component in this file (it's imported), so 'renders' edge won't be created for Button.
    // If we had two components in the file, it would.
  });
});
