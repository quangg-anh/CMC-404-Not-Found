import { useEffect, useRef, useState, type ReactNode } from 'react';

type RevealProps = {
  children: ReactNode;
  className?: string;
  /** Stagger index 0–5 */
  delay?: 0 | 1 | 2 | 3 | 4 | 5;
  as?: 'div' | 'section' | 'aside';
};

/**
 * Scroll-into-view reveal. Starts hidden, fades up once visible.
 * Respects prefers-reduced-motion via CSS (instant show).
 */
export function Reveal({ children, className = '', delay = 0, as: Tag = 'div' }: RevealProps) {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setVisible(true);
      return;
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          io.disconnect();
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const delayClass = delay > 0 ? `ls-in-delay-${delay}` : '';

  return (
    <Tag
      ref={ref as never}
      className={`ls-in ${visible ? 'ls-in-visible' : ''} ${delayClass} ${className}`.trim()}
    >
      {children}
    </Tag>
  );
}
