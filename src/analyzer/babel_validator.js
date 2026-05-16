#!/usr/usr/bin/env node
import fs from 'fs';
import * as parser from '@babel/parser';
import path from 'path';

// Tier 1 Validation: Babel parse
// Validates that an extracted file from PyDriller is structurally sound Javascript/Typescript.

const filepath = process.argv[2];

if (!filepath || !fs.existsSync(filepath)) {
    console.error("Missing or invalid filepath");
    process.exit(1);
}

try {
    const code = fs.readFileSync(filepath, 'utf8');
    
    // Attempt to parse it as modern JSX/TSX
    parser.parse(code, {
        sourceType: 'module',
        plugins: [
            'jsx',
            'typescript',
            'decorators-legacy',
            'classProperties'
        ]
    });
    
    // If it survives parsing, it is structurally valid syntax.
    console.log("VALID");
    process.exit(0);
} catch (err) {
    console.error(`INVALID: ${err.message}`);
    process.exit(1);
}
