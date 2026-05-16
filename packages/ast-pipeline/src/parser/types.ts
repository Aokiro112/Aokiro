import * as t from '@babel/types';

export interface ParsedEntity {
  name: string;
  loc?: t.SourceLocation | null;
}

export interface ParsedImport extends ParsedEntity {
  source: string;
  specifiers: string[];
}

export interface ParsedExport extends ParsedEntity {
  isDefault: boolean;
}

export interface ParsedHook extends ParsedEntity {
  arguments: string[];
}

export interface ParsedState extends ParsedEntity {
  setter: string;
  initialValue?: string;
}

export interface ParsedEffect extends ParsedEntity {
  dependencies?: string[];
}

export interface ParsedComponent extends ParsedEntity {
  props: string[];
  hooks: ParsedHook[];
  states: ParsedState[];
  effects: ParsedEffect[];
  jsxElements: ParsedJSX[];
  functionCalls: ParsedFunctionCall[];
}

export interface ParsedFunctionCall extends ParsedEntity {
  arguments: string[];
}

export interface ParsedJSX extends ParsedEntity {
  props: string[];
  childrenCount: number;
}

export interface ExtractedAST {
  imports: ParsedImport[];
  exports: ParsedExport[];
  components: ParsedComponent[];
  topLevelFunctions: ParsedFunctionCall[];
}
