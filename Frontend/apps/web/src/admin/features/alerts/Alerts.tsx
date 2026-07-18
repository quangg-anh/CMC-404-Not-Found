import { useEffect, useMemo, useState } from 'react';
import { MagnifyingGlass, ChartLineUp, Users, CheckCircle, Warning, CaretRight, Robot, Spinner, Link as LinkIcon } from '@phosphor-icons/react';
import { RiskBadge, type RiskLabel } from '../../../../../../packages/ui-legal/src/components/RiskBadge';
import { CitationCard } from '../../../../../../packages/ui-legal/src/components/CitationCard';
import { apiGet, apiPatch } from '../../../lib/api';
import { ErrorBanner, PageHeader } from '../../components/AdminChrome';

interface RawAlert {
  alert_id?: string;
  id?: string;
  chu_de?: string;
  chuDe?: string;
  claim?: string;
  noi_dung?: string;
  post_url?: string;
  postUrl?: string;
  volume?: number;
  label?: string;
  severity?: string;
  confidence?: 'high' | 'medium' | 'low';
  status?: string;
  created_at?: string;
  evidence?: { van_ban?: string; dieu?: string; quote?: string };
  provenance_status?: string;
  signals?: AlertSignal[];
}

interface AlertSignal {
  claim_text?: string;
  evidence_span?: string;
  post_url?: string;
  label?: RiskLabel;
  score?: number;
  legal_evidence?: { van_ban?: string; dieu?: string; quote?: string };
}

interface AlertsResponse {
  items: RawAlert[];
  total: number;
}

interface AlertView {
  id: string;
  chuDe: string;
  claim?: string;
  postUrl?: string;
  volume: number;
  label?: RiskLabel;
  confidence?: 'high' | 'medium' | 'low';
  status: string;
  createdAt: string;
  evidence?: { van_ban: string; dieu: string; quote: string };
  provenanceComplete: boolean;
}

function toLabel(raw: RawAlert, signal?: AlertSignal): RiskLabel | undefined {
  if (signal?.label === 'khop' || signal?.label === 'mau_thuan' || signal?.label === 'khong_ro') return signal.label;
  if (raw.label === 'khop' || raw.label === 'mau_thuan' || raw.label === 'khong_ro') return raw.label;
  return undefined;
}

function normalize(raw: RawAlert): AlertView {
  const signal = raw.signals?.[0];
  const ev = signal?.legal_evidence ?? raw.evidence;
  const score = signal?.score;
  return {
    id: raw.alert_id ?? raw.id ?? 'unknown',
    chuDe: raw.chu_de ?? raw.chuDe ?? 'Chủ đề chưa phân loại',
    claim: signal?.claim_text ?? raw.claim ?? raw.noi_dung,
    postUrl: signal?.post_url ?? raw.post_url ?? raw.postUrl,
    volume: raw.volume ?? 0,
    label: toLabel(raw, signal),
    confidence: raw.confidence ?? (score == null ? undefined : score >= 0.85 ? 'high' : score >= 0.7 ? 'medium' : 'low'),
    status: raw.status ?? 'open',
    createdAt: raw.created_at ?? '',
    evidence: ev && (ev.van_ban || ev.quote) ? { van_ban: ev.van_ban ?? '', dieu: ev.dieu ?? '', quote: ev.quote ?? '' } : undefined,
    provenanceComplete: raw.provenance_status === 'complete' && Boolean(signal),
  };
}

function LinkPreviewPanel({ url }: { url: string }) {
  try {
    const domain = new URL(url).hostname;
    return (
      <div className="mt-3 flex items-center gap-3 p-3 rounded-xl border border-slate-200 bg-white shadow-sm hover:shadow-md transition-shadow">
        <div className="w-10 h-10 bg-slate-50 rounded-lg flex items-center justify-center shrink-0 border border-slate-100">
          <LinkIcon size={20} className="text-slate-400" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-slate-800 truncate">{domain}</p>
          <a href={url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 hover:underline truncate block mt-0.5">
            {url}
          </a>
        </div>
      </div>
    );
  } catch {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="text-xs font-bold text-blue-600 hover:underline flex items-center gap-1 w-fit mt-3">
        Nguồn: {url}
      </a>
    );
  }
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    apiGet<AlertsResponse>('/admin/alerts')
      .then((data) => setAlerts((data.items ?? []).map(normalize)))
      .catch((err) => setError(err instanceof Error ? err.message : 'Lỗi tải cảnh báo'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const triage = async (id: string, action: 'dismiss' | 'create_suggest') => {
    setBusyId(id);
    try {
      await apiPatch(`/admin/alerts/${id}`, { action });
      setAlerts((prev) =>
        prev.map((a) =>
          a.id === id ? { ...a, status: action === 'dismiss' ? 'closed' : 'triaged' } : a,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi xử lý cảnh báo');
    } finally {
      setBusyId(null);
    }
  };

  const filtered = useMemo(
    () => alerts.filter((a) => !search || a.chuDe.toLowerCase().includes(search.toLowerCase()) || (a.claim ?? '').toLowerCase().includes(search.toLowerCase())),
    [alerts, search],
  );

  return (
    <div className="mx-auto max-w-6xl pb-20">
      <PageHeader
        title="Cảnh báo tin giả & sai lệch"
        subtitle="AI trích xuất nhận định pháp lý trên MXH và đối chiếu với cơ sở dữ liệu luật — số liệu từ API `/admin/alerts`."
        actions={
          <div className="relative">
            <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm chủ đề hoặc claim…"
              className="admin-input w-64 !py-2.5 pl-10"
            />
          </div>
        }
      />

      {error ? <div className="mb-6"><ErrorBanner message={error} /></div> : null}

      {loading ? (
        <div className="flex items-center justify-center gap-2 p-16 text-sm font-semibold text-muted">
          <Spinner size={20} className="animate-spin" aria-hidden /> Đang tải cảnh báo…
        </div>
      ) : filtered.length === 0 ? (
        <div className="admin-card p-16 text-center">
          <Warning size={40} className="mx-auto mb-4 text-border" weight="fill" aria-hidden />
          <p className="font-semibold text-muted">Chưa có cảnh báo nào được ghi nhận.</p>
          <p className="mt-1 text-sm text-muted">Cảnh báo xuất hiện khi pipeline giám sát MXH phát hiện tín hiệu sai lệch.</p>
        </div>
      ) : (
        <div className="space-y-5">
          {filtered.map((alert) => (
            <div key={alert.id} className="admin-card group overflow-hidden transition hover:border-primary/30">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/80 bg-background/60 px-6 py-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="rounded-control border border-border bg-white px-2 py-1 font-mono text-xs font-bold text-muted shadow-sm">{alert.id.slice(0, 8)}</span>
                  <span className="text-sm font-bold text-ink">{alert.chuDe}</span>
                  {alert.createdAt ? <span className="text-xs font-medium text-muted">• {alert.createdAt}</span> : null}
                </div>
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-2 text-xs font-semibold text-muted">
                    <ChartLineUp size={16} aria-hidden /> Volume:{' '}
                    <span className="font-bold text-ink">{alert.volume.toLocaleString('vi-VN')}</span>
                  </div>
                  <div className="h-4 w-px bg-border" />
                  <div className="flex items-center gap-2 text-xs font-semibold">
                    Trạng thái:
                    {alert.status === 'open' ? (
                      <span className="rounded-md border border-red-100 bg-red-50 px-2 py-0.5 text-red-600">Cần xử lý</span>
                    ) : (
                      <span className="rounded-md border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-emerald-600">
                        {alert.status === 'triaged' ? 'Đã triage' : 'Đã đóng'}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-8 relative">
                <div className="hidden lg:block absolute left-1/2 top-6 bottom-6 w-px bg-slate-100 -translate-x-1/2"></div>

                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-3">
                    <Users size={18} className="text-blue-500" weight="fill" />
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Nội dung lan truyền MXH</span>
                  </div>
                  <div className="bg-slate-50 rounded-xl p-5 border border-slate-200/60 mb-4 relative">
                    <p className="text-[15px] font-medium text-slate-800 leading-relaxed relative z-10 italic">
                      {alert.claim ?? 'Không có dữ liệu nguồn được liên kết.'}
                    </p>
                  </div>
                  {alert.postUrl && (
                    <LinkPreviewPanel url={alert.postUrl} />
                  )}
                </div>

                <div className="flex flex-col">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Robot size={18} className="text-brand" weight="fill" />
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-500">AI Đối chiếu Pháp luật</span>
                    </div>
                    {alert.label && alert.confidence ? (
                      <RiskBadge label={alert.label} confidence={alert.confidence} />
                    ) : (
                      <span className="text-xs font-bold text-slate-500 bg-slate-100 px-2 py-1 rounded-md">Chưa có kết quả NLI</span>
                    )}
                  </div>
                  {alert.evidence ? (
                    <CitationCard van_ban={alert.evidence.van_ban} dieu={alert.evidence.dieu} quote={alert.evidence.quote} />
                  ) : (
                    <div className="text-sm text-slate-400 italic bg-slate-50 rounded-xl p-5 border border-slate-100">Chưa tìm thấy căn cứ pháp lý đã xác thực.</div>
                  )}
                </div>
              </div>

              <div className="px-6 py-4 bg-slate-50/50 border-t border-slate-100 flex items-center justify-end gap-3">
                {alert.status === 'open' && (
                  <>
                    <button
                      onClick={() => triage(alert.id, 'dismiss')}
                      disabled={busyId === alert.id}
                      className="px-4 py-2 rounded-lg text-sm font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 shadow-sm transition-colors flex items-center gap-2 disabled:opacity-50"
                    >
                      <CheckCircle size={16} /> Bỏ qua (Đánh dấu an toàn)
                    </button>
                    <button
                      onClick={() => triage(alert.id, 'create_suggest')}
                      disabled={busyId === alert.id}
                      className="px-4 py-2 rounded-lg text-sm font-bold text-white bg-brand border border-brand hover:bg-red-700 shadow-md shadow-brand/20 transition-all flex items-center gap-2 disabled:opacity-50"
                    >
                      {busyId === alert.id ? <Spinner size={16} className="animate-spin" /> : null}
                      Sinh bài Đính chính <CaretRight size={16} weight="bold" />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
