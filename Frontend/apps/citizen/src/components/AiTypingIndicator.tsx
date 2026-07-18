import { useEffect, useState } from 'react';
import { BookOpen, MagnifyingGlass, PencilSimple, Scales, SpinnerGap } from '@phosphor-icons/react';

const STEPS = [
  { label: 'Đang tìm điều khoản liên quan…', Icon: MagnifyingGlass },
  { label: 'Đang đối chiếu căn cứ pháp lý…', Icon: BookOpen },
  { label: 'Đang soạn câu trả lời dễ hiểu…', Icon: PencilSimple },
] as const;

/** Rich waiting state while BE2/QA is generating an answer. */
export function AiTypingIndicator() {
  const [step, setStep] = useState(0);
  const [progress, setProgress] = useState(8);

  useEffect(() => {
    const stepId = window.setInterval(() => {
      setStep((i) => (i + 1) % STEPS.length);
    }, 2400);
    return () => window.clearInterval(stepId);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => {
      setProgress((p) => {
        if (p >= 92) return 18 + Math.random() * 12;
        return Math.min(92, p + 3 + Math.random() * 5);
      });
    }, 420);
    return () => window.clearInterval(id);
  }, []);

  const ActiveIcon = STEPS[step].Icon;

  return (
    <div
      className="ls-typing ls-typing-panel w-full min-w-[240px] sm:min-w-[300px]"
      role="status"
      aria-live="polite"
      aria-label="Đang chờ phản hồi từ trợ lý AI"
    >
      <div className="ls-typing-sweep" aria-hidden />

      <div className="relative mb-3 flex items-center gap-2.5">
        <div className="relative flex h-10 w-10 items-center justify-center rounded-[12px] bg-primary-soft text-primary">
          <Scales size={18} weight="fill" className="ls-typing-icon" aria-hidden />
          <span className="ls-typing-ring" aria-hidden />
          <span className="ls-typing-ring ls-typing-ring--delay" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-bold text-ink">
            Trợ lý đang trả lời
            <span className="ls-typing-live" aria-hidden />
          </p>
          <p key={step} className="ls-typing-status mt-0.5 flex items-center gap-1.5 truncate text-xs font-medium text-muted sm:text-sm">
            <ActiveIcon size={14} className="shrink-0 text-primary" weight="bold" aria-hidden />
            {STEPS[step].label}
          </p>
        </div>
        <div className="relative shrink-0" aria-hidden>
          <SpinnerGap size={22} className="animate-spin text-primary" weight="bold" />
        </div>
      </div>

      {/* Step pills */}
      <div className="relative mb-3 flex gap-1.5" aria-hidden>
        {STEPS.map((_, i) => (
          <span
            key={i}
            className={`ls-typing-step h-1.5 flex-1 rounded-full ${i <= step ? 'ls-typing-step--on' : ''}`}
          />
        ))}
      </div>

      {/* Progress */}
      <div className="relative mb-3 h-1.5 overflow-hidden rounded-full bg-primary-soft" aria-hidden>
        <div
          className="ls-typing-progress h-full rounded-full bg-gradient-to-r from-primary via-[#4F7FE8] to-accent"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Skeleton lines with shimmer */}
      <div className="relative space-y-2.5" aria-hidden>
        <div className="ls-skeleton-bar ls-skeleton-bar--glow h-3.5 w-[94%] rounded-full" />
        <div className="ls-skeleton-bar ls-skeleton-bar--glow h-3.5 w-[82%] rounded-full" style={{ animationDelay: '150ms' }} />
        <div className="ls-skeleton-bar ls-skeleton-bar--glow h-3.5 w-[68%] rounded-full" style={{ animationDelay: '300ms' }} />
        <div className="ls-skeleton-bar ls-skeleton-bar--glow h-3.5 w-[40%] rounded-full" style={{ animationDelay: '450ms' }} />
      </div>

      <div className="relative mt-3.5 flex items-center justify-between gap-2" aria-hidden>
        <div className="flex items-center gap-1.5">
          <span className="ls-dot-bounce h-2.5 w-2.5 rounded-full bg-primary" />
          <span className="ls-dot-bounce h-2.5 w-2.5 rounded-full bg-primary" style={{ animationDelay: '0.16s' }} />
          <span className="ls-dot-bounce h-2.5 w-2.5 rounded-full bg-accent" style={{ animationDelay: '0.32s' }} />
          <span className="ml-1.5 text-xs font-semibold text-primary">Đang xử lý</span>
        </div>
        <span className="tabular-nums text-[11px] font-bold text-muted">{Math.round(progress)}%</span>
      </div>
    </div>
  );
}
