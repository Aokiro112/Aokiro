import { createHash } from 'crypto';

export function generateDeterministicId(type: string, ...components: (string | number)[]): string {
  const hash = createHash('sha256');
  hash.update(type);
  components.forEach(c => {
    hash.update(String(c));
  });
  return type.toLowerCase() + '_' + hash.digest('hex').substring(0, 12);
}
