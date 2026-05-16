import { get_encoding } from "tiktoken";

const enc = get_encoding("cl100k_base");

export function countTokens(text) {
  const tokens = enc.encode(text);
  return tokens.length;
}

export function validateTokenLimit(text, limit = 3500) {
  const count = countTokens(text);
  if (count > limit) {
    throw new Error(`Token limit exceeded: ${count} > ${limit}`);
  }
  return count;
}
