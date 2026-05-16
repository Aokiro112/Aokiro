import crypto from 'crypto';

// Quality Gate Pipeline
// Ensures only high-signal, safe, balanced dataset rows make it to train.jsonl

const SEEN_HASHES = new Set();
let BALANCE_TRACKER = {
  memory_leak: 0,
  react_hook: 0,
  synthetic: 0,
  mined: 0
};

// We don't want any one category to exceed 40% of the dataset
const MAX_CATEGORY_PERCENTAGE = 0.40;

export function qualityGate(datasetRow, sourceCategory) {
  const { input, output } = datasetRow;

  // 1. Duplicate Detection (AST Content Hashing)
  const astContentMatch = input.match(/Context: (\{.*\})/s);
  if (!astContentMatch) return { pass: false, reason: "Malformed AST input" };
  
  const astHash = crypto.createHash('sha256').update(astContentMatch[1]).digest('hex');
  if (SEEN_HASHES.has(astHash)) {
     return { pass: false, reason: "Duplicate AST structure detected" };
  }
  
  // 2. Token Budget Enforcement (Approximate by length)
  // 3500 tokens is roughly 14,000 characters
  if (input.length > 14000) {
     return { pass: false, reason: "Exceeds token budget" };
  }

  // 3. Broken Patch Rejection
  // Simple heuristic: Diff must have @@ headers and at least one +/-
  if (!output.includes('@@') || (!output.includes('\n+') && !output.includes('\n-'))) {
     if (output.includes('No changes required')) {
        // This is fine for clean component examples
     } else {
        return { pass: false, reason: "Broken patch / Noisy diff" };
     }
  }

  // 4. Architecture Signal Scoring
  // If the AST has no hooks and no dependencies, it's too simple.
  const ast = JSON.parse(astContentMatch[1]);
  if ((!ast.hooks || ast.hooks.length === 0) && (!ast.children || ast.children.length === 0)) {
     return { pass: false, reason: "Low architecture signal (too simple)" };
  }

  // 5. Dataset Balance Enforcement
  const totalProcessed = Object.values(BALANCE_TRACKER).reduce((a, b) => a + b, 0) || 1;
  if (BALANCE_TRACKER[sourceCategory] / totalProcessed > MAX_CATEGORY_PERCENTAGE) {
     return { pass: false, reason: `Balance enforcement: ${sourceCategory} is overrepresented.` };
  }

  // Pass all gates
  SEEN_HASHES.add(astHash);
  BALANCE_TRACKER[sourceCategory]++;
  
  return { pass: true, reason: null };
}

export function printQualityMetrics() {
  console.log("=== Quality Gate Metrics ===");
  console.table(BALANCE_TRACKER);
  console.log(`Total Unique Valid Rows: ${SEEN_HASHES.size}`);
}
