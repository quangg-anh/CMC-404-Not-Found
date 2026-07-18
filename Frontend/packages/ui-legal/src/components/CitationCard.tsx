import React from 'react';
import { Scales, ArrowSquareOut, FileText, Hash, Article, BookOpen } from '@phosphor-icons/react';

interface CitationCardProps {
  khoan_id?: string;
  van_ban: string;
  dieu: string;
  quote?: string;
  url?: string;
}

function documentKind(text: string): string {
  const normalized = text.toLowerCase();
  if (normalized.includes('nghị định') || normalized.includes('/nd-cp') || normalized.includes('/nđ-cp')) return 'Nghị định';
  if (normalized.includes('luật') || normalized.includes('/qh')) return 'Luật';
  if (normalized.includes('thông tư') || normalized.includes('/tt-')) return 'Thông tư';
  if (normalized.includes('quyết định') || normalized.includes('/qd-') || normalized.includes('/qđ-')) return 'Quyết định';
  return 'Văn bản';
}

function extractDocumentNumber(khoanId: string | undefined, vanBan: string): string {
  const fromId = khoanId?.split('::')[0]?.trim();
  if (fromId) return fromId;

  const match = vanBan.match(/\b\d+\s*\/\s*\d{4}\s*\/\s*[A-ZĐĐa-zđ\-]+\b/u);
  return match?.[0]?.replace(/\s+/g, '') ?? vanBan;
}

function extractArticle(khoanId: string | undefined, dieu: string): string {
  const fromId = khoanId?.match(/::D(\d+)/i)?.[1];
  if (fromId) return `Điều ${fromId}`;
  const fromText = dieu.match(/Điều\s*\d+/i)?.[0];
  return fromText ?? (dieu || 'Chưa rõ điều');
}

function extractClause(khoanId: string | undefined, quote: string | undefined): string {
  const fromId = khoanId?.match(/\.K(\d+)/i)?.[1];
  if (fromId) return `Khoản ${fromId}`;
  const fromQuote = quote?.match(/(?:^|\s)(\d+)\s*[.)]\s+/)?.[1];
  return fromQuote ? `Khoản ${fromQuote}` : '—';
}

/** Compact legal ref card: số hiệu · Điều · Khoản only (no long quote body). */
export const CitationCard: React.FC<CitationCardProps> = ({ khoan_id, van_ban, dieu, quote, url }) => {
  const kind = documentKind(`${van_ban} ${khoan_id ?? ''}`);
  const documentNumber = extractDocumentNumber(khoan_id, van_ban);
  const article = extractArticle(khoan_id, dieu);
  const clause = extractClause(khoan_id, quote);
  const showQuote = Boolean(quote?.trim());

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm transition-all duration-300 hover:border-emerald-200 hover:shadow-md">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-emerald-500 via-cyan-500 to-blue-500" />

      <div className="px-4 pt-4 sm:px-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100">
              <Scales size={18} weight="fill" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-black uppercase tracking-wide text-white">
                  {kind}
                </span>
                {khoan_id ? (
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-bold text-slate-500">
                    {khoan_id}
                  </span>
                ) : null}
              </div>
              <div className="mt-1.5 flex items-center gap-2 text-xs font-semibold text-slate-500">
                <FileText size={14} weight="fill" className="shrink-0 text-slate-400" />
                <span className="truncate">{van_ban || documentNumber}</span>
              </div>
            </div>
          </div>
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl border border-slate-200 bg-white p-2 text-slate-400 transition-colors hover:border-emerald-200 hover:text-emerald-600"
              title="Mở chi tiết văn bản"
            >
              <ArrowSquareOut size={17} weight="bold" />
            </a>
          ) : null}
        </div>
      </div>

      <div className="grid gap-2 px-4 py-4 sm:grid-cols-3 sm:px-5">
        <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-blue-500">
            <BookOpen size={13} weight="fill" /> Văn bản
          </div>
          <div className="mt-1 text-sm font-black text-blue-950">{documentNumber}</div>
        </div>
        <div className="rounded-xl border border-emerald-100 bg-emerald-50/70 p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-emerald-500">
            <Article size={13} weight="fill" /> Điều
          </div>
          <div className="mt-1 text-sm font-black text-emerald-950">{article}</div>
        </div>
        <div className="rounded-xl border border-amber-100 bg-amber-50/80 p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-amber-500">
            <Hash size={13} weight="fill" /> Khoản
          </div>
          <div className="mt-1 text-sm font-black text-amber-950">{clause}</div>
        </div>
      </div>

      {showQuote ? (
        <div className="border-t border-slate-100 px-4 pb-4 sm:px-5">
          <p className="line-clamp-3 text-xs leading-relaxed text-slate-600">{quote}</p>
        </div>
      ) : null}
    </div>
  );
};
