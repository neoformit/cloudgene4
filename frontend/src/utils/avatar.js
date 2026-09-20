/**
 * Local initials avatar (no third-party request: the old gravatar URL sent raw e-mails out).
 */
export function initials(user) {
  const name = (user?.full_name || '').trim()
  const parts = name ? name.split(/\s+/) : [user?.username || '?']
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : parts[0].slice(0, 2)
  return letters.toUpperCase()
}

/** Stable hue per username, for the avatar background. */
export function avatarHue(user) {
  const s = user?.username || ''
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
  return h
}
