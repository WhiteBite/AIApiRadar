// ── Fingerprint helper ────────────────────────────────────────────────────────
// SHA-256 of CF-Connecting-IP + User-Agent — identifies a visitor without storing PII.
export async function fingerprint(req: Request): Promise<string> {
  const ip = req.headers.get('CF-Connecting-IP')
    ?? req.headers.get('X-Forwarded-For')?.split(',')[0]?.trim()
    ?? 'unknown';
  const ua = req.headers.get('User-Agent') ?? 'unknown';
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${ip}|${ua}`));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}
