/** Soft brand atmosphere — decorative only, keeps layout unchanged. */

type Tone = 'hero' | 'section' | 'chat' | 'band';

const TONE_CLASS: Record<Tone, string> = {
  hero: 'ls-atmosphere--hero',
  section: 'ls-atmosphere--section',
  chat: 'ls-atmosphere--chat',
  band: 'ls-atmosphere--band',
};

export function Atmosphere({
  tone = 'section',
  className = '',
  showMark = false,
}: {
  tone?: Tone;
  className?: string;
  /** Large soft scales watermark */
  showMark?: boolean;
}) {
  return (
    <div className={`ls-atmosphere ${TONE_CLASS[tone]} ${className}`} aria-hidden>
      <div className="ls-atmosphere__mesh" />
      <div className="ls-atmosphere__orb ls-atmosphere__orb--primary" />
      <div className="ls-atmosphere__orb ls-atmosphere__orb--accent" />
      <div className="ls-atmosphere__beam" />
      {showMark ? (
        <svg className="ls-atmosphere__mark" viewBox="0 0 120 120" fill="none">
          <path
            d="M60 18c-2.2 0-4 1.8-4 4v8H40a4 4 0 1 0 0 8h16v10.2c-9.4 1.4-16.6 9.5-16.6 19.3 0 10.8 8.8 19.5 19.6 19.5S79 78.3 79 67.5c0-9.8-7.2-17.9-16.6-19.3V38h16a4 4 0 1 0 0-8H64v-8c0-2.2-1.8-4-4-4Z"
            fill="currentColor"
            opacity="0.55"
          />
          <path
            d="M28 98h64M36 88h48"
            stroke="currentColor"
            strokeWidth="5"
            strokeLinecap="round"
            opacity="0.4"
          />
          <circle cx="44" cy="52" r="10" fill="currentColor" opacity="0.25" />
          <circle cx="76" cy="52" r="10" fill="currentColor" opacity="0.25" />
        </svg>
      ) : null}
      <div className="ls-atmosphere__grain" />
    </div>
  );
}

/** Small inline accent illustration for cards / asides */
export function AccentIllustration({
  variant = 'document',
}: {
  variant?: 'document' | 'shield' | 'chat';
}) {
  if (variant === 'shield') {
    return (
      <svg className="ls-illus" viewBox="0 0 80 80" fill="none" aria-hidden>
        <defs>
          <linearGradient id="ls-ill-g1" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
            <stop stopColor="#2557D6" stopOpacity="0.9" />
            <stop offset="1" stopColor="#E85D0F" stopOpacity="0.75" />
          </linearGradient>
        </defs>
        <path
          d="M40 10 64 20v18c0 16.5-10.8 28.6-24 32-13.2-3.4-24-15.5-24-32V20L40 10Z"
          fill="url(#ls-ill-g1)"
          opacity="0.18"
        />
        <path
          d="M40 18 58 26v14c0 12-8 21-18 24-10-3-18-12-18-24V26L40 18Z"
          stroke="url(#ls-ill-g1)"
          strokeWidth="2.2"
        />
        <path d="M32 40.5 38 46.5 50 34" stroke="#168A45" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  if (variant === 'chat') {
    return (
      <svg className="ls-illus" viewBox="0 0 80 80" fill="none" aria-hidden>
        <defs>
          <linearGradient id="ls-ill-g2" x1="10" y1="14" x2="70" y2="66" gradientUnits="userSpaceOnUse">
            <stop stopColor="#2557D6" />
            <stop offset="1" stopColor="#4F7FE8" />
          </linearGradient>
        </defs>
        <rect x="12" y="16" width="48" height="36" rx="12" fill="url(#ls-ill-g2)" opacity="0.16" />
        <rect x="18" y="22" width="36" height="24" rx="8" stroke="url(#ls-ill-g2)" strokeWidth="2" />
        <path d="M28 58h12l-4 8-8-8Z" fill="#E85D0F" opacity="0.55" />
        <circle cx="30" cy="34" r="2.5" fill="#2557D6" />
        <circle cx="40" cy="34" r="2.5" fill="#2557D6" />
        <circle cx="50" cy="34" r="2.5" fill="#E85D0F" />
      </svg>
    );
  }

  return (
    <svg className="ls-illus" viewBox="0 0 80 80" fill="none" aria-hidden>
      <defs>
        <linearGradient id="ls-ill-g3" x1="16" y1="10" x2="64" y2="70" gradientUnits="userSpaceOnUse">
          <stop stopColor="#2557D6" stopOpacity="0.85" />
          <stop offset="1" stopColor="#E85D0F" stopOpacity="0.7" />
        </linearGradient>
      </defs>
      <rect x="18" y="12" width="40" height="52" rx="8" fill="url(#ls-ill-g3)" opacity="0.14" />
      <rect x="22" y="16" width="32" height="44" rx="6" stroke="url(#ls-ill-g3)" strokeWidth="2" />
      <path d="M30 28h16M30 36h16M30 44h10" stroke="#2557D6" strokeWidth="2.2" strokeLinecap="round" opacity="0.55" />
      <circle cx="54" cy="54" r="10" fill="#E85D0F" opacity="0.2" />
      <path d="M50 54h8M54 50v8" stroke="#E85D0F" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
