import _traverse from '@babel/traverse';
import * as t from '@babel/types';
import {
  ExtractedAST,
  ParsedComponent,
  ParsedExport,
  ParsedImport,
  ParsedState,
  ParsedHook,
  ParsedEffect,
  ParsedJSX,
  ParsedFunctionCall
} from './types';

// Workaround for CJS/ESM interop with babel/traverse
const traverse = typeof _traverse === 'function' ? _traverse : (_traverse as any).default;

export function extractASTInfo(ast: t.File): ExtractedAST {
  const imports: ParsedImport[] = [];
  const exports: ParsedExport[] = [];
  const components: ParsedComponent[] = [];
  const topLevelFunctions: ParsedFunctionCall[] = [];

  // Helper to get name from node
  const getName = (node: t.Node | null | undefined): string => {
    if (!node) return '';
    if (t.isIdentifier(node)) return node.name;
    if (t.isStringLiteral(node)) return node.value;
    return 'Unknown';
  };

  traverse(ast, {
    ImportDeclaration(path: any) {
      const specifiers = path.node.specifiers.map((s: any) => s.local.name);
      imports.push({
        name: getName(path.node.source), // the module name
        source: path.node.source.value,
        specifiers,
        loc: path.node.loc
      });
    },
    ExportNamedDeclaration(path: any) {
      if (path.node.declaration) {
        if (t.isVariableDeclaration(path.node.declaration)) {
          path.node.declaration.declarations.forEach((d: any) => {
            exports.push({
              name: getName(d.id),
              isDefault: false,
              loc: path.node.loc
            });
          });
        } else if (t.isFunctionDeclaration(path.node.declaration) || t.isClassDeclaration(path.node.declaration)) {
          exports.push({
            name: getName(path.node.declaration.id),
            isDefault: false,
            loc: path.node.loc
          });
        }
      } else if (path.node.specifiers) {
        path.node.specifiers.forEach((s: any) => {
          exports.push({
            name: getName(s.exported),
            isDefault: false,
            loc: path.node.loc
          });
        });
      }
    },
    ExportDefaultDeclaration(path: any) {
      const decl = path.node.declaration;
      exports.push({
        name: getName(decl.id || decl),
        isDefault: true,
        loc: path.node.loc
      });
    },
    FunctionDeclaration(path: any) {
      // Check if it's a React component
      const isComponent = path.node.id?.name && /^[A-Z]/.test(path.node.id.name);
      if (isComponent) {
        components.push(extractComponent(path));
      }
    },
    VariableDeclarator(path: any) {
      if (t.isArrowFunctionExpression(path.node.init) || t.isFunctionExpression(path.node.init)) {
        const isComponent = path.node.id && t.isIdentifier(path.node.id) && /^[A-Z]/.test(path.node.id.name);
        if (isComponent) {
          components.push(extractComponent(path));
        }
      }
    }
  });

  return { imports, exports, components, topLevelFunctions };
}

function extractComponent(path: any): ParsedComponent {
  const node = path.node;
  let name = '';
  if (t.isFunctionDeclaration(node)) {
    name = node.id?.name || 'Anonymous';
  } else if (t.isVariableDeclarator(node) && t.isIdentifier(node.id)) {
    name = node.id.name;
  }

  const props: string[] = [];
  const functionNode = t.isFunctionDeclaration(node) ? node : node.init;
  if (functionNode && (functionNode.params?.length > 0)) {
    const firstParam = functionNode.params[0];
    if (t.isObjectPattern(firstParam)) {
      firstParam.properties.forEach((p: any) => {
        if (t.isObjectProperty(p) && t.isIdentifier(p.key)) {
          props.push(p.key.name);
        }
      });
    } else if (t.isIdentifier(firstParam)) {
      props.push(firstParam.name);
    }
  }

  const hooks: ParsedHook[] = [];
  const states: ParsedState[] = [];
  const effects: ParsedEffect[] = [];
  const jsxElements: ParsedJSX[] = [];
  const functionCalls: ParsedFunctionCall[] = [];

  if (functionNode && functionNode.body) {
    path.traverse({
      CallExpression(childPath: any) {
        const callee = childPath.node.callee;
        if (t.isIdentifier(callee)) {
          const funcName = callee.name;
          if (funcName.startsWith('use')) {
            if (funcName === 'useState') {
              const parent = childPath.parent;
              let stateName = '';
              let setterName = '';
              if (t.isVariableDeclarator(parent) && t.isArrayPattern(parent.id)) {
                const elems = parent.id.elements;
                if (elems[0] && t.isIdentifier(elems[0])) stateName = elems[0].name;
                if (elems[1] && t.isIdentifier(elems[1])) setterName = elems[1].name;
              }
              states.push({
                name: stateName,
                setter: setterName,
                loc: childPath.node.loc
              });
            } else if (funcName === 'useEffect') {
              let deps: string[] = [];
              const args = childPath.node.arguments;
              if (args.length > 1 && t.isArrayExpression(args[1])) {
                deps = args[1].elements.map((e: any) => e?.name).filter(Boolean);
              }
              effects.push({
                name: 'useEffect',
                dependencies: deps,
                loc: childPath.node.loc
              });
            } else {
              hooks.push({
                name: funcName,
                arguments: [], // simplistic argument extraction
                loc: childPath.node.loc
              });
            }
          } else {
            functionCalls.push({
              name: funcName,
              arguments: [],
              loc: childPath.node.loc
            });
          }
        }
      },
      JSXElement(childPath: any) {
        const opening = childPath.node.openingElement;
        let elementName = 'Unknown';
        if (t.isJSXIdentifier(opening.name)) {
          elementName = opening.name.name;
        } else if (t.isJSXMemberExpression(opening.name)) {
          elementName = `${(opening.name.object as any).name}.${opening.name.property.name}`;
        }
        
        const elementProps = opening.attributes
          .map((a: any) => t.isJSXAttribute(a) ? a.name.name : 'spread')
          .filter(Boolean) as string[];

        jsxElements.push({
          name: elementName,
          props: elementProps,
          childrenCount: childPath.node.children.length,
          loc: childPath.node.loc
        });
      }
    });
  }

  return {
    name,
    props,
    hooks,
    states,
    effects,
    jsxElements,
    functionCalls,
    loc: node.loc
  };
}
