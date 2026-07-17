import { useEffect, useMemo, useState } from 'react';
import { MagnifyingGlass, ChartLineUp, Users, CheckCircle, Warning, CaretRight, Robot, Spinner, Link as LinkIcon } from '@phosphor-icons/react';
import { RiskBadge, type RiskLabel } from '../../../../../packages/ui-legal/src/components/RiskBadge';
import { CitationCard } from '../../../../../packages/ui-legal/src/components/CitationCard';
import { apiGet, apiPatch } from '../../lib/api';

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
}

interface AlertsResponse {
  items: RawAlert[];
  total: number;
}

interface AlertView {
  id: string;
  chuDe: string;
  claim: string;
  postUrl?: string;
  volume: number;
  label: RiskLabel;
  confidence: 'high' | 'medium' | 'low';
  status: string;
  createdAt: string;
  evidence?: { van_ban: string; dieu: string; quote: string };
}

function toLabel(raw: RawAlert): RiskLabel {
  if (raw.label === 'khop' || raw.label === 'mau_thuan' || raw.label === 'khong_ro') return raw.label;
  if (raw.severity === 'high') return 'mau_thuan';
  return 'khong_ro';
}

function normalize(raw: RawAlert): AlertView {
  const ev = raw.evidence;
  return {
    id: raw.alert_id ?? raw.id ?? 'unknown',
    chuDe: raw.chu_de ?? raw.chuDe ?? 'Chủ đề chưa phân loại',
    claim: raw.claim ?? raw.noi_dung ?? '(Không có nội dung lan truyền)',
    postUrl: raw.post_url ?? raw.postUrl,
    volume: raw.volume ?? 0,
    label: toLabel(raw),
    confidence: raw.confidence ?? 'medium',
    status: raw.status ?? 'open',
    createdAt: raw.created_at ?? '',
    evidence: ev && (ev.van_ban || ev.quote) ? { van_ban: ev.van_ban ?? '', dieu: ev.dieu ?? '', quote: ev.quote ?? '' } : undefined,
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
      setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, status: action === 'dismiss' ? 'resolved' : 'investigating' } : a)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi xử lý cảnh báo');
    } finally {
      setBusyId(null);
    }
  };

  const filtered = useMemo(
    () => alerts.filter((a) => !search || a.chuDe.toLowerCase().includes(search.toLowerCase()) || a.claim.toLowerCase().includes(search.toLowerCase())),
    [alerts, search],
  );

  return (
    <div className="max-w-6xl mx-auto pb-20 animate-fade-in-up">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-10">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-xs font-bold uppercase tracking-widest mb-3">
            <Warning size={16} weight="fill" /> Radar Mạng Xã Hội
          </div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Cảnh báo Tin giả & Sai lệch</h1>
          <p className="text-slate-500 mt-2 font-medium">
            AI tự động trích xuất các nhận định pháp lý trên MXH và đối chiếu với cơ sở dữ liệu luật Quốc gia.
          </p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm kiếm chủ đề..."
              className="pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-medium w-64 focus:outline-none focus:border-brand transition-colors shadow-sm"
            />
          </div>
        </div>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-5 py-4 text-sm font-semibold mb-6">{error}</div>}

      {loading ? (
        <div className="p-16 text-center text-slate-400 font-semibold flex items-center justify-center gap-2">
          <Spinner size={20} className="animate-spin" /> Đang tải cảnh báo…
        </div>
      ) : filtered.length === 0 ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200">
          <Warning size={40} className="text-slate-300 mx-auto mb-4" weight="fill" />
          <p className="text-slate-500 font-semibold">Chưa có cảnh báo nào được ghi nhận.</p>
          <p className="text-slate-400 text-sm mt-1">Cảnh báo sẽ xuất hiện khi pipeline giám sát MXH phát hiện tín hiệu sai lệch.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {filtered.map((alert) => (
            <div key={alert.id} className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden flex flex-col hover:border-brand/30 transition-colors group">
              <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex flex-wrap gap-4 items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-black text-slate-400 bg-white px-2 py-1 rounded border border-slate-200 shadow-sm">{alert.id}</span>
                  <span className="text-sm font-bold text-slate-800">{alert.chuDe}</span>
                  {alert.createdAt && <span className="text-xs text-slate-500 font-medium">• {alert.createdAt}</span>}
                </div>
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                    <ChartLineUp size={16} /> Volume: <span className="text-slate-900 font-bold">{alert.volume.toLocaleString('vi-VN')}</span>
                  </div>
                  <div className="h-4 w-px bg-slate-300"></div>
                  <div className="flex items-center gap-2 text-xs font-semibold">
                    Trạng thái:
                    {alert.status === 'open' ? (
                      <span className="text-red-600 bg-red-50 px-2 py-0.5 rounded-md border border-red-100">Cần xử lý</span>
                    ) : (
                      <span className="text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-100">Đã xử lý</span>
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
                    <p className="text-[15px] font-medium text-slate-800 leading-relaxed relative z-10 italic">{alert.claim}</p>
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
                    <RiskBadge label={alert.label} confidence={alert.confidence} />
                  </div>
                  {alert.evidence ? (
                    <CitationCard van_ban={alert.evidence.van_ban} dieu={alert.evidence.dieu} quote={alert.evidence.quote} />
                  ) : (
                    <div className="text-sm text-slate-400 italic bg-slate-50 rounded-xl p-5 border border-slate-100">Chưa có căn cứ pháp lý đối chiếu.</div>
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
