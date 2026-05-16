import { parse } from '@babel/parser';
import * as t from '@babel/types';

export function parseFile(code: string): t.File {
  return parse(code, {
    sourceType: 'module',
    plugins: [
      'typescript',
      'jsx',
      'decorators-legacy',
      'classProperties'
    ]
  });
}
