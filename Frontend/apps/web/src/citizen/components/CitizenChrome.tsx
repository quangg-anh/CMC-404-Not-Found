import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Scales, MagnifyingGlass, Article, BookOpen, List, X, type Icon } from '@phosphor-icons/react';

const NAV: { to: string; label: string; icon: Icon; primary?: boolean }[] = [
  { to: '/ask', label: 'Hỏi trợ lý AI', icon: MagnifyingGlass, primary: true },
  { to: '/news', label: 'Tin tức', icon: Article },
  { to: '/van-ban', label: 'Văn bản', icon: BookOpen },
];

function isActive(pathname: string, to: string) {
  return pathname === to || (to !== '/' && pathname.startsWith(to));
}

export function CitizenHeader() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  return (
    <header className="ls-header-sheen sticky top-0 z-50 border-b border-white/40 bg-white/60 backdrop-blur-xl">
      <div className="ls-container flex h-[76px] items-center justify-between gap-4">
        <Link to="/" className="group flex min-h-touch items-center gap-3 rounded-control pr-1 transition duration-ui" aria-label="Về trang chủ LexSocial AI">
          <div className="relative flex h-11 w-11 items-center justify-center rounded-[14px] bg-gradient-to-br from-primary to-[#3B6FE8] text-white shadow-[0_8px_18px_-10px_rgba(37,87,214,0.7)] transition duration-ui group-hover:scale-105">
            <span className="pointer-events-none absolute inset-0 rounded-[14px] bg-gradient-to-tr from-transparent via-white/25 to-transparent opacity-60" aria-hidden />
            <Scales size={24} weight="fill" aria-hidden />
          </div>
          <div>
            <p className="font-display text-lg font-extrabold leading-none tracking-tight sm:text-xl">
              <span className="ls-brand-gradient">LexSocial AI</span>
            </p>
            <p className="mt-1 hidden text-xs font-medium text-muted sm:block">Pháp luật dễ hiểu cho mọi người</p>
          </div>
        </Link>

        <nav className="hidden items-center gap-2 md:flex" aria-label="Điều hướng chính">
          {NAV.map(({ to, label, icon: IconCmp, primary }) => {
            const active = isActive(pathname, to);
            if (primary) {
              return (
                <Link
                  key={to}
                  to={to}
                  aria-current={active ? 'page' : undefined}
                  className={`ls-btn-primary !min-h-[44px] !px-4 !text-sm ${active ? 'ring-2 ring-primary/25 ring-offset-2' : ''}`}
                >
                  <IconCmp size={18} weight="bold" aria-hidden />
                  {label}
                </Link>
              );
            }
            return (
              <Link
                key={to}
                to={to}
                aria-current={active ? 'page' : undefined}
                className={`inline-flex min-h-[44px] items-center gap-2 rounded-control px-3 text-sm font-semibold transition duration-ui ${
                  active ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-background hover:text-ink'
                }`}
              >
                <IconCmp size={18} weight={active ? 'fill' : 'bold'} aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>

        <button
          type="button"
          className="ls-btn-secondary !min-h-[44px] !px-3 md:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? 'Đóng menu' : 'Mở menu'}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X size={22} weight="bold" /> : <List size={22} weight="bold" />}
        </button>
      </div>

      {open ? (
        <div id="mobile-nav" className="ls-reveal border-t border-white/40 bg-white/60 backdrop-blur-xl md:hidden">
          <nav className="ls-container flex flex-col gap-2 py-4" aria-label="Menu điện thoại">
            {NAV.map(({ to, label, icon: IconCmp, primary }) => {
              const active = isActive(pathname, to);
              return (
                <Link
                  key={to}
                  to={to}
                  className={`${primary ? 'ls-btn-primary' : 'ls-btn-secondary'} w-full justify-start ${
                    active && !primary ? '!border-primary/30 !bg-primary-soft !text-primary' : ''
                  }`}
                >
                  <IconCmp size={20} weight="bold" aria-hidden />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      ) : null}
    </header>
  );
}

export function CitizenFooter() {
  return (
    <footer className="ls-footer-wash mt-auto border-t border-border">
      <div className="ls-container flex flex-col gap-3 py-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-gradient-to-br from-primary to-[#3B6FE8] text-white shadow-sm">
            <Scales size={18} weight="fill" aria-hidden />
          </div>
          <div>
            <p className="text-sm font-extrabold">
              <span className="ls-brand-gradient">LexSocial AI</span>
            </p>
            <p className="text-sm text-muted">Hỏi pháp luật kèm căn cứ — nên đối chiếu nguyên văn</p>
          </div>
        </div>
        <p className="text-sm text-muted">© 2026 LexSocial AI</p>
      </div>
    </footer>
  );
}

export const SUGGESTIONS = [
  'Nghỉ thai sản được bao nhiêu ngày?',
  'Mức phạt nồng độ cồn hiện nay?',
  'Thủ tục làm CCCD gắn chip?',
] as const;

export function SuggestionChips({
  items = SUGGESTIONS,
  onSelect,
  className = '',
  tinted = false,
}: {
  items?: readonly string[];
  onSelect: (q: string) => void;
  className?: string;
  tinted?: boolean;
}) {
  return (
    <div className={`-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 ${className}`} role="list" aria-label="Câu hỏi gợi ý">
      {items.map((q) => (
        <button
          key={q}
          type="button"
          role="listitem"
          onClick={() => onSelect(q)}
          className={`ls-chip whitespace-nowrap ${tinted ? 'ls-chip-tint' : ''}`}
        >
          {q}
        </button>
      ))}
    </div>
  );
}
