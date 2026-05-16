const fs = require('fs');
const { parseFile } = require('./packages/ast-pipeline/dist/parser/babel');
const { extractASTInfo } = require('./packages/ast-pipeline/dist/parser/extractor');
const { compressAST } = require('./packages/ast-pipeline/dist/compression/compressor');

const chatJs = fs.readFileSync('./project_chat_application/client/src/components/Chat/Chat.js', 'utf-8');
const indexJs = fs.readFileSync('./project_chat_application/server/index.js', 'utf-8');

console.log('--- Chat.js ---');
const chatAst = parseFile(chatJs);
const chatExtracted = extractASTInfo(chatAst);
const chatCompressed = compressAST(chatExtracted);
console.log(JSON.stringify(Object.values(chatCompressed).filter(n => n.type === 'SocketEvent'), null, 2));

console.log('\n--- index.js ---');
const indexAst = parseFile(indexJs);
const indexExtracted = extractASTInfo(indexAst);
const indexCompressed = compressAST(indexExtracted);
console.log(JSON.stringify(Object.values(indexCompressed).filter(n => n.type === 'SocketEvent'), null, 2));
