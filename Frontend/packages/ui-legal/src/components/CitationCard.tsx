import React, { useState } from 'react';
import {
  ArrowSquareOut,
  CaretDown,
  CheckCircle,
  ClockCounterClockwise,
  Quotes,
  Scales,
} from '@phosphor-icons/react';

export interface CitationCardProps {
  /** v1 compatibility alias. New callers should use node_id. */
  khoan_id?: string;
  node_id?: string;
  lineage_id?: string;
  level?: 'dieu' | 'khoan' | 'diem';
  van_ban?: string;
  document_number?: string;
  dieu?: string;
  article?: string;
  clause?: string;
  point?: string;
  quote?: string;
  effective_from?: string;
  effective_to?: string;
  as_of?: string;
  support_status?: 'entailed' | 'unsupported' | 'needs_review';
  entailment_score?: number;
  validation_source?: 'neo4j';
  supports_claim_ids?: string[];
  url?: string;
  onOpenTimeline?: () => void;
}

function documentKind(text: string): string {
  const normalized = text.toLowerCase();
  if (normalized.includes('nghị định') || normalized.includes('/nd-cp') || normalized.includes('/nđ-cp')) return 'Nghị định';
  if (normalized.includes('luật') || normalized.includes('/qh')) return 'Luật';
  if (normalized.includes('thông tư') || normalized.includes('/tt-')) return 'Thông tư';
  if (normalized.includes('quyết định') || normalized.includes('/qd-') || normalized.includes('/qđ-')) return 'Quyết định';
  return 'Văn bản';
}

function extractDocumentNumber(identifier: string | undefined, document: string): string {
  const fromId = identifier?.split('::')[0]?.trim();
  if (fromId) return fromId;
  const match = document.match(/\b\d+\s*\/\s*\d{4}\s*\/\s*[A-ZĐĐa-zđ\-]+\b/u);
  return match?.[0]?.replace(/\s+/g, '') ?? document;
}

function extractArticle(identifier: string | undefined, value: string): string {
  const fromId = identifier?.match(/::D([^.@#]+)/i)?.[1];
  if (fromId) return fromId;
  return value.match(/Điều\s*([0-9a-zđ]+)/iu)?.[1] ?? value;
}

function extractClause(identifier: string | undefined, value?: string): string | undefined {
  return identifier?.match(/\.K([^.@#]+)/i)?.[1] ?? value;
}

function extractPoint(identifier: string | undefined, value?: string): string | undefined {
  return identifier?.match(/\.P([^.@#]+)/i)?.[1] ?? value;
}

function formatDate(value?: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('vi-VN');
}

function supportLabel(status?: CitationCardProps['support_status']): string | undefined {
  if (status === 'entailed') return 'Hỗ trợ trực tiếp';
  if (status === 'needs_review') return 'Cần kiểm tra';
  if (status === 'unsupported') return 'Không đủ hỗ trợ';
  return undefined;
}

/** Legal citation card supporting both the legacy Khoản response and Citation Contract v2. */
export const CitationCard: React.FC<CitationCardProps> = ({
  khoan_id,
  node_id,
  lineage_id,
  level,
  van_ban = '',
  document_number,
  dieu = '',
  article,
  clause,
  point,
  quote,
  effective_from,
  effective_to,
  as_of,
  support_status,
  entailment_score,
  validation_source,
  supports_claim_ids = [],
  url,
  onOpenTimeline,
}) => {
  const [expanded, setExpanded] = useState(false);
  const identifier = node_id ?? khoan_id;
  const documentNumber = document_number || extractDocumentNumber(identifier, van_ban);
  const articleNumber = article || extractArticle(identifier, dieu);
  const clauseNumber = extractClause(identifier, clause);
  const pointNumber = extractPoint(identifier, point);
  const kind = documentKind(`${documentNumber} ${van_ban}`);
  const statusLabel = supportLabel(support_status);
  const hasV2Metadata = Boolean(node_id || effective_from || validation_source);
  const effectiveLabel = effective_from
    ? `${formatDate(effective_from)} – ${effective_to ? formatDate(effective_to) : 'hiện tại'}`
    : undefined;

  return (
    <article className="group relative overflow-hidden rounded-[14px] border border-slate-200/80 bg-white shadow-sm transition-all duration-300 hover:border-emerald-300 hover:shadow-md">
      <div className="absolute bottom-0 left-0 top-0 w-1 bg-gradient-to-b from-emerald-500 via-cyan-500 to-blue-500 opacity-90" />

      <div className="flex items-start gap-3 py-3 pl-4 pr-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100">
          <Scales size={18} weight="fill" aria-hidden />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-[5px] border border-emerald-200/80 bg-emerald-50 px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wider text-emerald-800">
              {kind}
            </span>
            <span className="truncate text-sm font-black text-slate-800">{documentNumber || 'Chưa rõ văn bản'}</span>
            {statusLabel ? (
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                support_status === 'entailed'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-amber-200 bg-amber-50 text-amber-700'
              }`}>
                <CheckCircle size={12} weight="fill" aria-hidden />
                {statusLabel}
                {typeof entailment_score === 'number' ? ` ${Math.round(entailment_score * 100)}%` : ''}
              </span>
            ) : null}
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-semibold text-slate-600">
            {articleNumber ? <span>Điều {articleNumber}</span> : null}
            {clauseNumber ? <><span className="text-slate-300">•</span><span>Khoản {clauseNumber}</span></> : null}
            {pointNumber ? <><span className="text-slate-300">•</span><span>Điểm {pointNumber}</span></> : null}
            {level ? <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-slate-500">{level}</span> : null}
          </div>

          {hasV2Metadata ? (
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-semibold text-slate-500">
              {effectiveLabel ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-1 text-blue-700">
                  <ClockCounterClockwise size={13} weight="bold" aria-hidden />
                  Hiệu lực: {effectiveLabel}
                </span>
              ) : null}
              {as_of ? <span className="rounded-md bg-slate-100 px-2 py-1">Tại ngày {formatDate(as_of)}</span> : null}
              {validation_source === 'neo4j' ? (
                <span className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-700">Nguồn gốc đã xác minh</span>
              ) : null}
            </div>
          ) : null}

          {quote ? (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-slate-500 transition hover:text-emerald-700"
              aria-expanded={expanded}
            >
              <Quotes size={14} weight="fill" aria-hidden />
              {expanded ? 'Ẩn nguyên văn' : 'Xem nguyên văn'}
              <CaretDown size={12} weight="bold" className={`transition ${expanded ? 'rotate-180' : ''}`} aria-hidden />
            </button>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {onOpenTimeline && identifier ? (
            <button
              type="button"
              onClick={onOpenTimeline}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
              title="Xem lịch sử hiệu lực và so sánh phiên bản"
              aria-label="Xem lịch sử hiệu lực và so sánh phiên bản"
            >
              <ClockCounterClockwise size={17} weight="bold" />
            </button>
          ) : null}
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700"
              title="Mở chi tiết văn bản"
              aria-label="Mở chi tiết văn bản"
            >
              <ArrowSquareOut size={17} weight="bold" />
            </a>
          ) : null}
        </div>
      </div>

      {expanded && quote ? (
        <div className="border-t border-slate-100 bg-slate-50/80 px-5 py-4">
          <blockquote className="border-l-2 border-emerald-400 pl-3 text-sm leading-6 text-slate-700">
            {quote}
          </blockquote>
          {identifier ? <p className="mt-2 break-all text-[10px] font-mono text-slate-400">Node: {identifier}</p> : null}
          {lineage_id ? <p className="mt-1 break-all text-[10px] font-mono text-slate-400">Lineage: {lineage_id}</p> : null}
          {supports_claim_ids.length ? (
            <p className="mt-2 text-[11px] font-semibold text-slate-500">
              Hỗ trợ claim: {supports_claim_ids.join(', ')}
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
};
