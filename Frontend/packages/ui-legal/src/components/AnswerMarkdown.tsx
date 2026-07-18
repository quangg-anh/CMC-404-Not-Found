import React from 'react';

/** Insert newlines before section labels / bullets when the model smashes them onto one line. */
export function normalizeAnswerMarkdown(content: string): string {
  let text = (content || '').replace(/\r\n/g, '\n').trim();
  // BE2 style: **Kết luận ngắn:**  (colon inside the bold markers)
  text = text.replace(/(?!^)(?=\*\*[^*]{1,80}?:\*\*)/g, '\n\n');
  // Alternate: **Kết luận ngắn**:  (colon after closing **)
  text = text.replace(/(?!^)(?=\*\*[^*]{1,80}\*\*\s*:)/g, '\n\n');
  // Smash-fix bullets: "...text. - [id] ..."
  text = text.replace(/\s+(-\s+)/g, '\n$1');
  return text.replace(/\n{3,}/g, '\n\n').trim();
}

/** Turn every **bold** span into <strong>; leaves surrounding text untouched. */
export function renderInlineMarkdown(text: string): React.ReactNode {
  if (!text) return null;
  const parts = text.split(/(\*\*[^*]+?\*\*)/g);
  return parts.map((part, idx) => {
    if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={idx} className="font-bold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

type AnswerMarkdownProps = {
  content: string;
  className?: string;
  /** Slightly denser styling for the admin console. */
  density?: 'comfortable' | 'compact';
};

/**
 * Renders LLM answers that use light Markdown (**bold**, - bullets, --- rules).
 * Used by both citizen Ask and admin QA so ** markers never show raw.
 */
export function AnswerMarkdown({ content, className, density = 'comfortable' }: AnswerMarkdownProps) {
  const normalized = normalizeAnswerMarkdown(content);
  const lines = normalized.split('\n').map((line) => line.trim()).filter(Boolean);

  const bodyClass =
    density === 'compact'
      ? 'text-sm leading-7 text-slate-700'
      : 'text-[15px] sm:text-[16px] leading-relaxed text-slate-700';
  const bulletTextClass =
    density === 'compact'
      ? 'text-sm leading-6 text-slate-700'
      : 'text-[15px] leading-relaxed text-slate-700';

  if (lines.length === 0) {
    return null;
  }

  const hasStructure = lines.some(
    (line) => line.startsWith('- ') || line.includes('**') || line === '---',
  );

  if (!hasStructure) {
    return (
      <p className={`${bodyClass} whitespace-pre-wrap ${className || ''}`.trim()}>
        {normalized}
      </p>
    );
  }

  return (
    <div className={`space-y-3 ${className || ''}`.trim()}>
      {lines.map((line, idx) => {
        if (line === '---') {
          return (
            <div
              key={idx}
              className="my-3 h-px bg-gradient-to-r from-transparent via-slate-200 to-transparent"
            />
          );
        }

        if (line.startsWith('- ')) {
          return (
            <div
              key={idx}
              className="flex gap-3 rounded-xl bg-slate-50/90 px-3.5 py-2.5 ring-1 ring-slate-100/90 transition-colors duration-200"
            >
              <div className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
              <p className={bulletTextClass}>{renderInlineMarkdown(line.slice(2))}</p>
            </div>
          );
        }

        // **Heading:** rest…  OR  **Heading**: rest…
        const sectionMatch =
          line.match(/^\*\*([^*]+?):\*\*\s*(.*)$/) ||
          line.match(/^\*\*([^*]+?)\*\*\s*:\s*(.*)$/);

        if (sectionMatch) {
          const title = sectionMatch[1].replace(/:$/, '').trim();
          const rest = (sectionMatch[2] || '').trim();
          // If the remainder still has another section header, render inline (normalize should have split).
          if (rest.includes('**:') || /\*\*[^*]+?:\*\*/.test(rest)) {
            return (
              <p key={idx} className={bodyClass}>
                {renderInlineMarkdown(line)}
              </p>
            );
          }
          return (
            <div key={idx} className="space-y-2">
              <div className="mt-1 flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-50 to-sky-50/80 px-3.5 py-2 text-blue-900 ring-1 ring-blue-100/80 first:mt-0">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-600" aria-hidden />
                <h3 className="text-sm font-bold tracking-wide">{title}</h3>
              </div>
              {rest ? <p className={bodyClass}>{renderInlineMarkdown(rest)}</p> : null}
            </div>
          );
        }

        return (
          <p key={idx} className={bodyClass}>
            {renderInlineMarkdown(line)}
          </p>
        );
      })}
    </div>
  );
}
