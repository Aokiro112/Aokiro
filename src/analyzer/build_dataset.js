import fs from 'fs';
import path from 'path';

const SYSTEM_PROMPT = "You are Architect-JS. You receive compressed AST graphs. Output reasoning in <thought> and exact code patches in <diff>.";

function buildDataset() {
  const astDir = path.join(process.cwd(), 'data', 'test_ast');
  const manualFixesPath = path.join(process.cwd(), 'data', 'manual_fixes.json');
  const outputPath = path.join(process.cwd(), 'data', 'train.jsonl');

  if (!fs.existsSync(manualFixesPath)) {
    console.error("Missing manual_fixes.json");
    process.exit(1);
  }

  const manualFixes = JSON.parse(fs.readFileSync(manualFixesPath, 'utf8'));
  const astFiles = fs.readdirSync(astDir).filter(f => f.endsWith('.json'));

  const jsonlLines = [];
  let successCount = 0;

  for (const file of astFiles) {
    const componentName = file.replace('.json', '');
    const fixData = manualFixes[componentName];

    if (!fixData) {
      console.warn(`Skipping ${componentName}: No manual fix found.`);
      continue;
    }

    const astContent = fs.readFileSync(path.join(astDir, file), 'utf8');
    
    // Schema validation
    const ast = JSON.parse(astContent);
    if (!ast.imports || !ast.exports || !ast.hooks) {
       console.error(`Invalid AST schema in ${file}`);
       continue;
    }
    
    if (astContent.length < 10) {
       console.error(`AST too small in ${file}`);
       continue;
    }

    const inputString = `User: Analyze this component.\nContext: ${astContent}`;
    const outputString = `${fixData.thought}\n${fixData.diff}`;

    // Ensure correct XML tags exist
    if (!outputString.includes('<thought>') || !outputString.includes('<diff>')) {
        console.error(`Missing XML tags in manual fix for ${componentName}`);
        continue;
    }

    const row = {
      system: SYSTEM_PROMPT,
      input: inputString,
      output: outputString
    };

    jsonlLines.push(JSON.stringify(row));
    successCount++;
  }

  fs.writeFileSync(outputPath, jsonlLines.join('\n'));
  console.log(`\n[SUCCESS] Compiled ${successCount} perfectly validated SFT rows into data/train.jsonl`);
}

buildDataset();
