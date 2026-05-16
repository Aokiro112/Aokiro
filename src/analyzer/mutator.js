import jscodeshift from 'jscodeshift';
import fs from 'fs';

// Advanced Synthetic Mutation Engine
// Applies deterministic, safe architectural flaws to clean code.

const MUTATION_TYPES = [
  'stale_closure', 
  'hook_order_violation', 
  'missing_cleanup', 
  'prop_drilling',
  'state_explosion'
];

let diversityTracker = {
  stale_closure: 0,
  hook_order_violation: 0,
  missing_cleanup: 0,
  prop_drilling: 0,
  state_explosion: 0,
  failed_safety_check: 0
};

export function mutateComponent(codeString, type) {
  const j = jscodeshift;
  const root = j(codeString);
  let mutated = false;

  try {
    if (type === 'missing_cleanup') {
      // Find useEffects with return statements and remove the return statement
      root.find(j.CallExpression, { callee: { name: 'useEffect' } })
        .forEach(path => {
          const arrowFunc = path.value.arguments[0];
          if (arrowFunc && arrowFunc.body && arrowFunc.body.body) {
             const bodyArray = arrowFunc.body.body;
             const returnIdx = bodyArray.findIndex(n => n.type === 'ReturnStatement');
             if (returnIdx > -1) {
               bodyArray.splice(returnIdx, 1);
               mutated = true;
             }
          }
        });
    }

    if (type === 'hook_order_violation') {
       // Wrap a hook in an if statement (highly illegal in React)
       root.find(j.CallExpression, { callee: { name: 'useEffect' } })
         .forEach(path => {
            // A simplified AST mutation just for demonstration:
            // if (Math.random() > 0.5) { useEffect(...) }
            const originalEffect = path.node;
            const ifStatement = j.ifStatement(
                j.binaryExpression('>', j.callExpression(j.memberExpression(j.identifier('Math'), j.identifier('random')), []), j.literal(0.5)),
                j.blockStatement([j.expressionStatement(originalEffect)])
            );
            j(path).replaceWith(ifStatement);
            mutated = true;
         });
    }

    // Safety Control: Ensure the file still compiles via simple parser checks
    const finalCode = root.toSource();
    if (!validateMutationSafety(finalCode)) {
       diversityTracker.failed_safety_check++;
       return null;
    }

    if (mutated) {
       diversityTracker[type]++;
       return finalCode;
    }
    
    return null;

  } catch (err) {
    diversityTracker.failed_safety_check++;
    return null;
  }
}

function validateMutationSafety(code) {
  // We parse it again to ensure we didn't output syntactically impossible code
  try {
    jscodeshift(code);
    return true;
  } catch(e) {
    return false;
  }
}

export function printDiversityMetrics() {
  console.log("=== Mutation Diversity Tracking ===");
  console.table(diversityTracker);
}
