import { get_encoding, Tiktoken } from 'tiktoken';

let enc: Tiktoken | null = null;

export function getEncoder(): Tiktoken {
  if (!enc) {
    enc = get_encoding('cl100k_base');
  }
  return enc;
}

export function estimateTokens(text: string): number {
  return getEncoder().encode(text).length;
}

export function freeTokenizer() {
  if (enc) {
    enc.free();
    enc = null;
  }
}
