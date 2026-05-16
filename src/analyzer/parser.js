import { parse } from "@babel/parser";
import _traverse from "@babel/traverse";
const traverse = _traverse.default || _traverse;

export function extractAST(code, filename = "unknown") {
  const ast = parse(code, {
    sourceType: "module",
    plugins: ["jsx", "typescript", "decorators-legacy"],
  });

  const result = {
    file: filename,
    exports: [],
    imports: [],
    hooks: [],
    deps: {},
    children: []
  };

  const hookNames = new Set();
  const childElements = new Set();
  const importsSet = new Set();
  const exportsSet = new Set();

  traverse(ast, {
    ImportDeclaration(path) {
      importsSet.add(path.node.source.value);
    },
    ExportNamedDeclaration(path) {
      if (path.node.declaration) {
        if (path.node.declaration.type === "VariableDeclaration") {
          path.node.declaration.declarations.forEach(d => {
            if (d.id && d.id.name) exportsSet.add(d.id.name);
          });
        } else if (path.node.declaration.id && path.node.declaration.id.name) {
          exportsSet.add(path.node.declaration.id.name);
        }
      }
    },
    ExportDefaultDeclaration(path) {
      if (path.node.declaration && path.node.declaration.name) {
        exportsSet.add(path.node.declaration.name);
      } else if (path.node.declaration.id && path.node.declaration.id.name) {
        exportsSet.add(path.node.declaration.id.name);
      } else {
        exportsSet.add("default");
      }
    },
    CallExpression(path) {
      const callee = path.node.callee;
      if (callee.type === "Identifier" && callee.name.startsWith("use")) {
        hookNames.add(callee.name);
        // Check for dependency array in hooks like useEffect, useCallback, useMemo
        if (["useEffect", "useCallback", "useMemo"].includes(callee.name)) {
          if (path.node.arguments.length > 1) {
            const depsArg = path.node.arguments[1];
            if (depsArg.type === "ArrayExpression") {
              const deps = depsArg.elements.map(e => {
                if (!e) return null;
                if (e.type === "Identifier") return e.name;
                if (e.type === "MemberExpression") {
                   if (e.object.type === "Identifier" && e.property.type === "Identifier") {
                       return `${e.object.name}.${e.property.name}`;
                   }
                }
                return "ComplexExpression";
              }).filter(Boolean);
              
              result.deps[callee.name] = result.deps[callee.name] || [];
              result.deps[callee.name].push(...deps);
            }
          }
        }
      }
    },
    JSXElement(path) {
      const openingElement = path.node.openingElement;
      if (openingElement.name.type === "JSXIdentifier") {
        const name = openingElement.name.name;
        // Check if it's a component (starts with capital letter)
        if (name[0] === name[0].toUpperCase()) {
          childElements.add(name);
        }
      } else if (openingElement.name.type === "JSXMemberExpression") {
        if (openingElement.name.object.type === "JSXIdentifier" && openingElement.name.property.type === "JSXIdentifier") {
            childElements.add(`${openingElement.name.object.name}.${openingElement.name.property.name}`);
        }
      }
    }
  });

  result.imports = Array.from(importsSet);
  result.exports = Array.from(exportsSet);
  result.hooks = Array.from(hookNames);
  result.children = Array.from(childElements);

  // deduplicate deps and remove complex expression placeholder
  for (const hook in result.deps) {
    result.deps[hook] = Array.from(new Set(result.deps[hook])).filter(d => d !== "ComplexExpression");
  }

  return result;
}
