/**
 * Theme Token & Hardcoded-Color Guard (hadoku / @wolffm/themes compatible).
 *
 * Verifies:
 * 1. Zero hardcoded hex colors (#abc / #aabbcc) appear in src/ or tailwind.config.js.
 * 2. Every CSS custom property var(--...) referenced in src/ or tailwind.config.js
 *    belongs to the canonical @wolffm/themes vocabulary.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');

const ALLOWED_THEME_VARS = new Set([
  '--color-bg',
  '--color-bg-alt',
  '--color-bg-card',
  '--color-bg-hover',
  '--color-bg-overlay',
  '--color-border',
  '--color-border-light',
  '--color-danger',
  '--color-danger-bg',
  '--color-danger-dark',
  '--color-neutral',
  '--color-neutral-bg',
  '--color-on-danger',
  '--color-on-danger-bg',
  '--color-on-primary',
  '--color-on-primary-bg',
  '--color-on-success-bg',
  '--color-on-warning-bg',
  '--color-primary',
  '--color-primary-bg',
  '--color-primary-dark',
  '--color-primary-hover',
  '--color-success',
  '--color-success-bg',
  '--color-success-dark',
  '--color-text',
  '--color-text-secondary',
  '--color-text-tertiary',
  '--color-warning',
  '--color-warning-bg',
  '--font-family',
  '--font-weight-bold',
  '--font-weight-normal',
  '--font-weight-semibold',
  '--hdk-radius',
  '--hdk-radius-lg',
  '--hdk-radius-sm',
  '--hdk-shadow-focus-sm',
  '--hdk-shadow-lg',
  '--hdk-shadow-md',
  '--hdk-shadow-sm',
  '--hdk-space-3xl',
  '--hdk-space-lg',
  '--hdk-space-md',
  '--hdk-space-sm',
  '--hdk-space-xl',
  '--hdk-space-xs',
  '--hdk-text-base',
  '--hdk-text-lg',
  '--hdk-text-md',
  '--hdk-text-sm',
  '--hdk-text-xs',
  '--is-dark-theme',
]);

function walkFiles(dir, extFilter) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkFiles(full, extFilter));
    } else if (extFilter.some((ext) => entry.name.endsWith(ext))) {
      results.push(full);
    }
  }
  return results;
}

const filesToCheck = [
  ...walkFiles(path.join(rootDir, 'src'), ['.ts', '.tsx', '.css', '.js', '.jsx']),
  path.join(rootDir, 'tailwind.config.js'),
];

const HEX_RE = /#[0-9a-fA-F]{3,8}\b/g;
const VAR_RE = /var\(\s*(--[a-zA-Z0-9-]+)\s*\)/g;

let errors = 0;

for (const file of filesToCheck) {
  if (!fs.existsSync(file)) continue;
  const rel = path.relative(rootDir, file);
  const content = fs.readFileSync(file, 'utf8');
  const lines = content.split(/\r?\n/);

  lines.forEach((line, idx) => {
    // Skip comment lines
    const trimmed = line.trim();
    if (trimmed.startsWith('//') || trimmed.startsWith('/*') || trimmed.startsWith('*')) return;

    for (const match of line.matchAll(HEX_RE)) {
      console.error(`[theme-lint] Hardcoded hex color '${match[0]}' in ${rel}:${idx + 1}`);
      errors++;
    }

    for (const match of line.matchAll(VAR_RE)) {
      const token = match[1];
      if (!ALLOWED_THEME_VARS.has(token)) {
        console.error(`[theme-lint] Unknown theme token '${token}' in ${rel}:${idx + 1}`);
        errors++;
      }
    }
  });
}

if (errors > 0) {
  console.error(`\nFailed theme token check with ${errors} error(s).`);
  process.exit(1);
} else {
  console.log(`[theme-lint] Passed: ${filesToCheck.length} files verified with zero hardcoded colors and valid @wolffm/themes tokens.`);
}
