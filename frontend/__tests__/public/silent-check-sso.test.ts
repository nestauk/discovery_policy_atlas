import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

describe('silent-check-sso.html', () => {
  it('exists in public and posts message to parent', () => {
    const currentDir = path.dirname(fileURLToPath(import.meta.url));
    const filePath = path.resolve(currentDir, '../../public/silent-check-sso.html');

    expect(fs.existsSync(filePath)).toBe(true);

    const contents = fs.readFileSync(filePath, 'utf-8');
    expect(contents).toContain('parent.postMessage');
  });
});
