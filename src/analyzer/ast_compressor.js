#!/usr/bin/env node

import fs from 'fs';
import { Command } from 'commander';
import { extractAST } from './parser.js';
import { validateTokenLimit } from './utils/token_counter.js';
import path from 'path';

const program = new Command();

program
  .name('ast_compressor')
  .description('Compress React/TSX files into high-signal AST JSON')
  .version('1.0.0')
  .argument('<filepath>', 'path to the file to compress')
  .option('-l, --limit <number>', 'Token limit for the output JSON', 3500)
  .action((filepath, options) => {
    try {
      const absolutePath = path.resolve(filepath);
      if (!fs.existsSync(absolutePath)) {
        console.error(`Error: File not found at ${absolutePath}`);
        process.exit(1);
      }

      const code = fs.readFileSync(absolutePath, 'utf8');
      const filename = path.basename(absolutePath);

      // Parse the code
      const compressedAST = extractAST(code, filename);

      // Convert to minimal JSON string
      const jsonString = JSON.stringify(compressedAST, null, 2);

      // Validate tokens
      const limit = parseInt(options.limit, 10);
      const tokenCount = validateTokenLimit(jsonString, limit);

      console.log(jsonString);
      console.error(`\n[SUCCESS] Token count: ${tokenCount}/${limit}`);

    } catch (error) {
      console.error(`\n[ERROR] ${error.message}`);
      process.exit(1);
    }
  });

program.parse();
