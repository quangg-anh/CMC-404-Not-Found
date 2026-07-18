import type { Icon } from '@phosphor-icons/react';
import { Spinner } from '@phosphor-icons/react';

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="admin-heading-accent font-display text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
          {title}
        </h1>
        {subtitle ? <p className="mt-2 max-w-2xl text-sm text-muted sm:text-base">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon: IconCmp,
  tone = 'primary',
  loading,
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon: Icon;
  tone?: 'primary' | 'accent' | 'success' | 'danger' | 'warning';
  loading?: boolean;
}) {
  const tones: Record<string, string> = {
    primary: 'from-primary to-[#4F7FE8]',
    accent: 'from-accent to-[#F08A4B]',
    success: 'from-success to-[#34C759]',
    danger: 'from-destructive to-[#F87171]',
    warning: 'from-warning to-[#F59E0B]',
  };

  return (
    <div className="admin-card relative overflow-hidden p-5">
      <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-primary/[0.04]" />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-muted">{label}</p>
          <p className="mt-1 font-display text-3xl font-extrabold tracking-tight text-ink">
            {loading ? '—' : value}
          </p>
          {hint ? <p className="mt-2 text-sm font-medium text-muted">{hint}</p> : null}
        </div>
        <div
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br text-white shadow-sm ${tones[tone]}`}
        >
          <IconCmp size={22} weight="fill" aria-hidden />
        </div>
      </div>
    </div>
  );
}

export function LoadingBlock({ label = 'Đang tải…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm font-semibold text-muted">
      <Spinner size={18} className="animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-control border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
      {message}
    </div>
  );
}
