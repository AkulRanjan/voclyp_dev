export const API_BASE =
  process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

export function wsUrl(path: string, token: string): string {
  const base = API_BASE.replace(/^http/, 'ws');
  const sep = path.includes('?') ? '&' : '?';
  return `${base}${path}${sep}token=${encodeURIComponent(token)}`;
}

export const BRAND = {
  indigo: '#3d2bff',
  amber: '#ffb347',
  navy: '#0a0f1e',
  background: '#fafafa',
  muted: '#71717a',
  border: '#e4e4e7',
};
