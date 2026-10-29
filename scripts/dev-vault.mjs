#!/usr/bin/env node
/**
 * Zero-.env Secret Broker (dev-vault).
 *
 * Reads .devvault.json from the workspace root and resolves secrets in-memory
 * using a single local bootstrap key (HADOKU_VAULT_KEY or BWS_ACCESS_TOKEN)
 * against the public vault endpoint (HADOKU_VAULT_URL) or Bitwarden CLI before
 * spawning the target command.
 *
 * Usage:
 *   node scripts/dev-vault.mjs -- vite
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const manifestPath = path.join(rootDir, '.devvault.json');

async function resolveVaultSecrets() {
  if (!fs.existsSync(manifestPath)) return {};

  const raw = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const entries = Object.entries(raw).filter(([k]) => !k.startsWith('//'));
  const bootstrapKey = process.env.HADOKU_VAULT_KEY || process.env.BWS_ACCESS_TOKEN;
  const vaultUrl = process.env.HADOKU_VAULT_URL || 'https://hadoku.me/api/vault/resolve';

  if (!bootstrapKey) {
    // Local standalone fallback when no remote bootstrap key is set yet
    return {};
  }

  try {
    const res = await fetch(vaultUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${bootstrapKey}`,
        'X-User-Key': bootstrapKey,
      },
      body: JSON.stringify({
        keys: entries.map(([, vaultKey]) => vaultKey),
      }),
    });
    if (!res.ok) {
      console.warn(`[dev-vault] Vault endpoint returned HTTP ${res.status}; continuing with current environment.`);
      return {};
    }
    const data = await res.json();
    const resolved = {};
    for (const [envName, vaultKey] of entries) {
      if (data && data[vaultKey]) {
        resolved[envName] = data[vaultKey];
      }
    }
    return resolved;
  } catch (err) {
    console.warn(`[dev-vault] Could not reach vault (${err.message}); continuing in local mode.`);
    return {};
  }
}

async function main() {
  const args = process.argv.slice(2);
  const sepIdx = args.indexOf('--');
  const cmdArgs = sepIdx >= 0 ? args.slice(sepIdx + 1) : args;

  if (cmdArgs.length === 0) {
    console.error('Usage: node scripts/dev-vault.mjs -- <command> [args...]');
    process.exit(1);
  }

  const injected = await resolveVaultSecrets();
  const child = spawn(cmdArgs[0], cmdArgs.slice(1), {
    stdio: 'inherit',
    shell: true,
    env: {
      ...process.env,
      ...injected,
    },
  });

  child.on('exit', (code) => {
    process.exit(code ?? 0);
  });
}

main();
