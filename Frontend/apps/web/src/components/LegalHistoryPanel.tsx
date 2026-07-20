import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowsLeftRight,
  CheckCircle,
  ClockCounterClockwise,
  SpinnerGap,
  WarningCircle,
  X,
} from '@phosphor-icons/react';
import { KhoanViewer } from '../../../../packages/ui-legal/src/components/KhoanViewer';
import { apiGet } from '../lib/api';
import type { NormalizedCitation } from '../lib/qaContract';
import { formatLegalCoordinate } from '../lib/qaContract';

interface ProvisionVersion {
  provision_id: string;
  lineage_id: string;
  version_no: number;
  source_vb_id: string;
  logical_vb_id: string;
  article: string;
  clause?: string;
  point?: string;
  text: string;
  effective_from: string;
  effective_to?: string;
}

interface TimelineResponse {
  identifier: string;
  lineage_id: string;
  items: ProvisionVersion[];
  transitions: Array<{
    old_id: string;
    new_id: string;
    relation_present: boolean;
    interval_contiguous: boolean;
  }>;
  complete_chain: boolean;
  total: number;
}

interface DiffHunk {
  type: 'replace' | 'delete' | 'insert';
  old: string;
  new: string;
}

interface CompareResponse {
  old: ProvisionVersion;
  new: ProvisionVersion;
  diff: {
    status: string;
    total_hunks: number;
    hunks: DiffHunk[];
  };
}

interface LegalHistoryPanelProps {
  citation: NormalizedCitation | null;
  audience: 'admin' | 'citizen';
  onClose: () => void;
}

function formatDate(value?: string): string {
  if (!value) return 'hiện tại';
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('vi-VN');
}

function endpoint(audience: 'admin' | 'citizen', identifier: string): string {
  return `/${audience}/legal/provisions/${encodeURIComponent(identifier)}/timeline`;
}

function compareEndpoint(audience: 'admin' | 'citizen', oldId: string, newId: string): string {
  const query = new URLSearchParams({ old_id: oldId, new_id: newId });
  return `/${audience}/legal/provisions/compare?${query.toString()}`;
}

export function LegalHistoryPanel({ citation, audience, onClose }: LegalHistoryPanelProps) {
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const identifier = citation?.nodeId ?? citation?.lineageId ?? citation?.khoanId;

  useEffect(() => {
    if (!citation) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previousFocus?.focus();
    };
  }, [citation, onClose]);

  useEffect(() => {
    if (!citation || !identifier) return;
    let cancelled = false;
    setLoading(true);
    setTimeline(null);
    setComparison(null);
    setSelectedId(citation.nodeId ?? null);
    setError(null);
    void apiGet<TimelineResponse>(endpoint(audience, identifier))
      .then((result) => {
        if (cancelled) return;
        setTimeline(result);
        setSelectedId((current) =>
          current && result.items.some((item) => item.provision_id === current)
            ? current
            : result.items.at(-1)?.provision_id ?? null,
        );
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'Không tải được lịch sử hiệu lực.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [audience, citation, identifier]);

  const selectedIndex = useMemo(
    () => timeline?.items.findIndex((item) => item.provision_id === selectedId) ?? -1,
    [selectedId, timeline],
  );
  const selected = selectedIndex >= 0 ? timeline?.items[selectedIndex] : undefined;
  const previous = selectedIndex > 0 ? timeline?.items[selectedIndex - 1] : undefined;

  if (!citation) return null;

  const compare = async () => {
    if (!previous || !selected) return;
    setCompareLoading(true);
    setComparison(null);
    setError(null);
    try {
      setComparison(
        await apiGet<CompareResponse>(
          compareEndpoint(audience, previous.provision_id, selected.provision_id),
        ),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Không thể so sánh hai phiên bản.');
    } finally {
      setCompareLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-slate-950/45 p-0 backdrop-blur-sm sm:items-center sm:p-5">
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="legal-history-title"
        className="flex max-h-[92dvh] w-full max-w-4xl flex-col overflow-hidden rounded-t-[28px] border border-white/70 bg-white shadow-2xl sm:rounded-[28px]"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-gradient-to-r from-slate-950 to-blue-950 px-5 py-4 text-white sm:px-6">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-cyan-200">
              <ClockCounterClockwise size={16} weight="bold" />
              Temporal law
            </div>
            <h2 id="legal-history-title" className="mt-1 text-xl font-black">Lịch sử hiệu lực</h2>
            <p className="mt-1 text-sm text-slate-300">
              {citation.documentNumber} · {formatLegalCoordinate(citation)}
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/10 transition hover:bg-white/20"
            aria-label="Đóng lịch sử hiệu lực"
          >
            <X size={20} weight="bold" />
          </button>
        </header>

        <div className="overflow-y-auto bg-slate-50 p-4 sm:p-6">
          {loading ? (
            <div className="flex min-h-52 items-center justify-center gap-3 text-sm font-bold text-blue-700">
              <SpinnerGap size={22} className="animate-spin" weight="bold" />
              Đang tải chuỗi phiên bản…
            </div>
          ) : error && !timeline ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-semibold text-amber-900">
              <div className="flex items-start gap-2">
                <WarningCircle size={20} weight="fill" className="mt-0.5 shrink-0" />
                <p>{error}</p>
              </div>
            </div>
          ) : timeline ? (
            <div className="space-y-5">
              <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-black text-slate-900">Chuỗi phiên bản</h3>
                  <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold ${
                    timeline.complete_chain
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-amber-50 text-amber-700'
                  }`}>
                    {timeline.complete_chain ? <CheckCircle size={14} weight="fill" /> : <WarningCircle size={14} weight="fill" />}
                    {timeline.complete_chain ? 'Chuỗi đầy đủ' : 'Cần kiểm tra chuỗi'}
                  </span>
                </div>
                <div className="mt-4 grid gap-2">
                  {timeline.items.map((item) => {
                    const activeAtQuestion = citation.asOf
                      ? item.effective_from <= citation.asOf &&
                        (!item.effective_to || citation.asOf < item.effective_to)
                      : item.provision_id === citation.nodeId;
                    return (
                      <button
                        type="button"
                        key={item.provision_id}
                        onClick={() => {
                          setSelectedId(item.provision_id);
                          setComparison(null);
                        }}
                        className={`flex w-full items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left transition ${
                          item.provision_id === selectedId
                            ? 'border-blue-300 bg-blue-50 ring-2 ring-blue-100'
                            : 'border-slate-200 bg-white hover:border-blue-200'
                        }`}
                      >
                        <span>
                          <span className="block text-sm font-black text-slate-800">Phiên bản {item.version_no}</span>
                          <span className="mt-0.5 block text-xs font-semibold text-slate-500">
                            {formatDate(item.effective_from)} – {formatDate(item.effective_to)}
                          </span>
                        </span>
                        {activeAtQuestion ? (
                          <span className="rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-bold text-emerald-800">
                            Hiệu lực tại ngày hỏi
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </div>

              {selected ? (
                <KhoanViewer
                  vanBanSoHieu={selected.source_vb_id}
                  dieuKhoan={[
                    `Điều ${selected.article}`,
                    selected.clause ? `Khoản ${selected.clause}` : '',
                    selected.point ? `Điểm ${selected.point}` : '',
                  ].filter(Boolean).join(', ')}
                  noiDung={selected.text}
                  effectiveFrom={selected.effective_from}
                  effectiveTo={selected.effective_to}
                  versionNo={selected.version_no}
                />
              ) : null}

              {previous && selected ? (
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="font-black text-slate-900">So sánh với phiên bản trước</h3>
                      <p className="mt-1 text-xs font-semibold text-slate-500">
                        Phiên bản {previous.version_no} → {selected.version_no}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void compare()}
                      disabled={compareLoading}
                      className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-bold text-white transition hover:bg-blue-700 disabled:opacity-50"
                    >
                      {compareLoading
                        ? <SpinnerGap size={16} className="animate-spin" weight="bold" />
                        : <ArrowsLeftRight size={16} weight="bold" />}
                      So sánh
                    </button>
                  </div>

                  {comparison ? (
                    <div className="mt-4 space-y-2">
                      {comparison.diff.hunks.length === 0 ? (
                        <p className="rounded-xl bg-slate-50 p-3 text-sm font-semibold text-slate-600">
                          Không có khác biệt nội dung.
                        </p>
                      ) : comparison.diff.hunks.map((hunk, index) => (
                        <div key={`${hunk.type}-${index}`} className="grid gap-2 rounded-xl border border-slate-200 p-3 sm:grid-cols-2">
                          <div className="rounded-lg bg-rose-50 p-3 text-sm text-rose-900">
                            <span className="mb-1 block text-[10px] font-black uppercase tracking-wide text-rose-600">Bản cũ</span>
                            {hunk.old || '—'}
                          </div>
                          <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">
                            <span className="mb-1 block text-[10px] font-black uppercase tracking-wide text-emerald-600">Bản mới</span>
                            {hunk.new || '—'}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {error ? <p className="text-sm font-semibold text-amber-700">{error}</p> : null}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
