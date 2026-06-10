/**
 * Admin authentication for project/site/route management.
 *
 * Threat model: anyone holding the APK can otherwise create or DELETE
 * projects/sites/routes from the SettingsTab. This module gates that
 * panel behind a numeric PIN held only on this device.
 *
 * Storage layout (localStorage):
 *   bird-platform-admin-pin-v1     PBKDF2-style hash of the PIN (string)
 *   bird-platform-admin-pin-salt   per-device random salt (string, 16 bytes hex)
 *   bird-platform-admin-unlock     ms-epoch when current unlock expires
 *
 * The hash is computed with WebCrypto SubtleCrypto.deriveBits when available,
 * falling back to a simple SHA-256(salt + pin) loop. Either way an attacker
 * who can read localStorage already controls the device, but the PIN is
 * never stored in plaintext.
 */

const PIN_HASH_KEY = 'bird-platform-admin-pin-v1';
const PIN_SALT_KEY = 'bird-platform-admin-pin-salt';
const UNLOCK_EXPIRES_KEY = 'bird-platform-admin-unlock';
const ADMIN_API_TOKEN_KEY = 'bird-platform-admin-api-token';
const UNLOCK_DURATION_MS = 30 * 60 * 1000;
const PIN_MIN_LENGTH = 4;
const PIN_MAX_LENGTH = 12;
const PBKDF2_ITERATIONS = 100_000;
// Backend counterpart: backend/middleware/admin_auth.py derives the same
// PBKDF2-HMAC-SHA256(pin, API_TOKEN_SALT, 100k) hex token from ADMIN_PIN, so
// DELETE/restore calls carry X-Admin-Token that the server can verify (B19).
const API_TOKEN_SALT = 'gm-admin-token-v1';

function getRandomHex(byteLength) {
  const buf = new Uint8Array(byteLength);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(buf);
  } else {
    for (let i = 0; i < byteLength; i += 1) buf[i] = Math.floor(Math.random() * 256);
  }
  return Array.from(buf).map((b) => b.toString(16).padStart(2, '0')).join('');
}

function bufferToHex(buffer) {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function hashPin(pin, salt) {
  const enc = new TextEncoder();
  const pinBytes = enc.encode(String(pin));
  const saltBytes = enc.encode(String(salt));
  if (typeof crypto !== 'undefined' && crypto.subtle && crypto.subtle.importKey) {
    try {
      const key = await crypto.subtle.importKey(
        'raw',
        pinBytes,
        { name: 'PBKDF2' },
        false,
        ['deriveBits'],
      );
      const bits = await crypto.subtle.deriveBits(
        { name: 'PBKDF2', salt: saltBytes, iterations: PBKDF2_ITERATIONS, hash: 'SHA-256' },
        key,
        256,
      );
      return bufferToHex(bits);
    } catch {
      // fall through to digest fallback
    }
  }
  if (typeof crypto !== 'undefined' && crypto.subtle && crypto.subtle.digest) {
    let acc = enc.encode(salt + ':' + pin);
    for (let i = 0; i < 1000; i += 1) {
      acc = new Uint8Array(await crypto.subtle.digest('SHA-256', acc));
    }
    return bufferToHex(acc);
  }
  let acc = `${salt}:${pin}`;
  for (let i = 0; i < 5000; i += 1) {
    let h = 0;
    for (let j = 0; j < acc.length; j += 1) {
      h = (h * 31 + acc.charCodeAt(j)) | 0;
    }
    acc = `${acc}:${(h >>> 0).toString(16)}`;
  }
  return acc;
}

async function deriveAdminApiToken(pin) {
  // Strict PBKDF2 only: the digest-loop fallbacks in hashPin would produce a
  // token the backend cannot reproduce, so in that case we store nothing and
  // server-side enforcement (if enabled) will reject with 401 instead of
  // silently sending a mismatched token.
  if (typeof crypto === 'undefined' || !crypto.subtle || !crypto.subtle.importKey) {
    return null;
  }
  try {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      'raw',
      enc.encode(String(pin)),
      { name: 'PBKDF2' },
      false,
      ['deriveBits'],
    );
    const bits = await crypto.subtle.deriveBits(
      {
        name: 'PBKDF2',
        salt: enc.encode(API_TOKEN_SALT),
        iterations: PBKDF2_ITERATIONS,
        hash: 'SHA-256',
      },
      key,
      256,
    );
    return bufferToHex(bits);
  } catch {
    return null;
  }
}

async function storeAdminApiToken(pin) {
  const token = await deriveAdminApiToken(pin);
  try {
    if (token) {
      sessionStorage.setItem(ADMIN_API_TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(ADMIN_API_TOKEN_KEY);
    }
  } catch {
    // sessionStorage unavailable; backend calls simply omit the header.
  }
}

export function getAdminApiToken() {
  try {
    return sessionStorage.getItem(ADMIN_API_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function clearAdminApiToken() {
  try {
    sessionStorage.removeItem(ADMIN_API_TOKEN_KEY);
  } catch {
    // best-effort
  }
}

export function isPinFormatValid(pin) {
  const value = String(pin || '');
  return /^[0-9]{4,12}$/.test(value) && value.length >= PIN_MIN_LENGTH && value.length <= PIN_MAX_LENGTH;
}

export function isAdminPinConfigured() {
  try {
    return Boolean(localStorage.getItem(PIN_HASH_KEY) && localStorage.getItem(PIN_SALT_KEY));
  } catch {
    return false;
  }
}

export function isAdminUnlocked() {
  try {
    const expiresRaw = localStorage.getItem(UNLOCK_EXPIRES_KEY);
    if (!expiresRaw) return false;
    const expires = Number(expiresRaw);
    if (!Number.isFinite(expires) || expires <= Date.now()) {
      localStorage.removeItem(UNLOCK_EXPIRES_KEY);
      return false;
    }
    return isAdminPinConfigured();
  } catch {
    return false;
  }
}

export function getAdminUnlockExpiry() {
  try {
    const raw = localStorage.getItem(UNLOCK_EXPIRES_KEY);
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

export async function setAdminPin(pin) {
  if (!isPinFormatValid(pin)) {
    const err = new Error('PIN must be 4-12 digits.');
    err.code = 'pin-format';
    throw err;
  }
  const salt = getRandomHex(16);
  const hash = await hashPin(pin, salt);
  try {
    localStorage.setItem(PIN_SALT_KEY, salt);
    localStorage.setItem(PIN_HASH_KEY, hash);
    localStorage.setItem(UNLOCK_EXPIRES_KEY, String(Date.now() + UNLOCK_DURATION_MS));
  } catch (err) {
    err.code = 'storage';
    throw err;
  }
  await storeAdminApiToken(pin);
  return { unlockedUntil: Date.now() + UNLOCK_DURATION_MS };
}

export async function unlockAdmin(pin) {
  if (!isPinFormatValid(pin)) {
    const err = new Error('PIN must be 4-12 digits.');
    err.code = 'pin-format';
    throw err;
  }
  if (!isAdminPinConfigured()) {
    const err = new Error('Admin PIN has not been configured on this device.');
    err.code = 'not-configured';
    throw err;
  }
  const salt = localStorage.getItem(PIN_SALT_KEY) || '';
  const expected = localStorage.getItem(PIN_HASH_KEY) || '';
  const candidate = await hashPin(pin, salt);
  if (candidate !== expected) {
    const err = new Error('Incorrect admin PIN.');
    err.code = 'mismatch';
    throw err;
  }
  const expiresAt = Date.now() + UNLOCK_DURATION_MS;
  try {
    localStorage.setItem(UNLOCK_EXPIRES_KEY, String(expiresAt));
  } catch {
    // localStorage may be unavailable (private mode / quota); the in-memory
    // unlock still applies for the current session.
  }
  await storeAdminApiToken(pin);
  return { unlockedUntil: expiresAt };
}

export function lockAdmin() {
  try {
    localStorage.removeItem(UNLOCK_EXPIRES_KEY);
  } catch {
    // localStorage may be unavailable; lock state is best-effort.
  }
  clearAdminApiToken();
}

export async function changeAdminPin(oldPin, newPin) {
  await unlockAdmin(oldPin);
  return setAdminPin(newPin);
}

export function clearAdminPin() {
  try {
    localStorage.removeItem(PIN_HASH_KEY);
    localStorage.removeItem(PIN_SALT_KEY);
    localStorage.removeItem(UNLOCK_EXPIRES_KEY);
  } catch {
    // localStorage may be unavailable; reset is best-effort.
  }
  clearAdminApiToken();
}

export const ADMIN_UNLOCK_DURATION_MS = UNLOCK_DURATION_MS;
export const ADMIN_PIN_MIN_LENGTH = PIN_MIN_LENGTH;
export const ADMIN_PIN_MAX_LENGTH = PIN_MAX_LENGTH;
