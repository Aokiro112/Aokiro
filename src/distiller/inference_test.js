import fs from 'fs';
import path from 'path';

// This script expects a local llama.cpp server running on port 8080
// Command to run: ./llama-server -m architect-js-1.5b-unsloth.Q4_K_M.gguf -c 2048 --port 8080

async function testInference() {
  const testFile = path.join(process.cwd(), 'data', 'unseen_test.json');
  if (!fs.existsSync(testFile)) {
    console.error("Test file missing!");
    process.exit(1);
  }

  const testData = JSON.parse(fs.readFileSync(testFile, 'utf8'));
  
  // Format as ChatML
  const prompt = `<|im_start|>system\n${testData.system}<|im_end|>\n<|im_start|>user\n${testData.input}<|im_end|>\n<|im_start|>assistant\n`;

  console.log("Sending unseen AST to local llama.cpp server...");
  const startTime = Date.now();

  try {
    const response = await fetch('http://localhost:8080/completion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt,
        n_predict: 512,
        temperature: 0.1, // Low temp for deterministic output
        stop: ["<|im_end|>"]
      })
    });

    if (!response.ok) {
       console.log("llama.cpp server not responding. Is it running?");
       return;
    }

    const result = await response.json();
    const endTime = Date.now();
    const latency = endTime - startTime;
    const outputText = result.content;
    const tokens = result.tokens_predicted;

    console.log(`\n=== MODEL OUTPUT ===\n${outputText}\n====================\n`);

    evaluateOutput(outputText, latency, tokens);

  } catch (err) {
    console.error("\n[!] Connection failed. Make sure `./llama-server` is running on port 8080 with the exported GGUF file.");
  }
}

function evaluateOutput(text, latency, tokens) {
  let score = 100;
  console.log("=== EVALUATION RESULTS ===");
  
  // 1. Strict <thought> parsing
  const thoughtMatch = text.match(/<thought>([\s\S]*?)<\/thought>/);
  if (thoughtMatch) {
    console.log("✅ <thought> block found and correctly closed.");
  } else {
    console.log("❌ <thought> block missing or malformed.");
    score -= 30;
  }

  // 2. Strict <diff> parsing
  const diffMatch = text.match(/<diff>([\s\S]*?)<\/diff>/);
  if (diffMatch) {
    console.log("✅ <diff> block found and correctly closed.");
  } else {
    console.log("❌ <diff> block missing or malformed.");
    score -= 30;
  }

  // 3. Conversational Filler Detection
  // Strip the XML tags and check if anything else is left
  let stripped = text.replace(/<thought>[\s\S]*?<\/thought>/, '')
                     .replace(/<diff>[\s\S]*?<\/diff>/, '')
                     .trim();
  
  if (stripped.length > 0) {
    console.log(`❌ Conversational filler detected: "${stripped}"`);
    score -= 40;
  } else {
    console.log("✅ Zero conversational filler detected.");
  }

  // Benchmarks
  console.log(`\n=== BENCHMARKS ===`);
  console.log(`Latency:       ${latency} ms`);
  console.log(`Token Usage:   ${tokens} tokens`);
  console.log(`Speed:         ${(tokens / (latency / 1000)).toFixed(2)} tokens/sec`);
  
  console.log(`\nFINAL PROTOCOL COMPLIANCE SCORE: ${score}/100`);
  if (score === 100) {
     console.log("[SUCCESS] Model perfectly learned the Architect-JS protocol!");
  } else {
     console.log("[FAIL] Model requires more SFT or stricter prompt distillation.");
  }
}

testInference();
