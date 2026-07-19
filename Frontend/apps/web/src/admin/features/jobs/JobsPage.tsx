import { useEffect, useState } from 'react';
import { PlayCircle, CheckCircle, XCircle, Clock, Spinner, ArrowsClockwise, HardDrives, StopCircle, WarningCircle, FileText } from '@phosphor-icons/react';
import { apiGet } from '../../../lib/api';

interface JobItem {
  job_id: string;
  type: string;
  status: string;
  payload: Record<string, unknown>;
  error: unknown;
  created_at: string | null;
  needs_review?: boolean;
}
interface JobsSummary { total_running: number; total_queued?: number; total_failed: number; total_needs_review: number; health: string }
interface JobsResponse { items: JobItem[]; total: number; summary: JobsSummary }

function getStatusConfig(status: string) {
  switch (status) {
    case 'running': return { icon: <Spinner className="animate-spin text-blue-500" size={20} />, color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200', label: 'Đang chạy' };
    case 'queued': return { icon: <Clock weight="fill" className="text-slate-400" size={20} />, color: 'text-slate-700', bg: 'bg-slate-100 border-slate-200', label: 'Trong hàng đợi' };
    case 'success': return { icon: <CheckCircle weight="fill" className="text-emerald-500" size={20} />, color: 'text-emerald-700', bg: 'bg-emerald-50 border-emerald-200', label: 'Hoàn thành' };
    case 'error':
    case 'failed': return { icon: <XCircle weight="fill" className="text-red-500" size={20} />, color: 'text-red-700', bg: 'bg-red-50 border-red-200', label: 'Lỗi' };
    case 'needs_review': return { icon: <StopCircle weight="fill" className="text-amber-500" size={20} />, color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200', label: 'Cần duyệt' };
    default: return { icon: <PlayCircle size={20} />, color: 'text-slate-700', bg: 'bg-slate-100 border-slate-200', label: status };
  }
}

const TYPE_LABELS: Record<string, string> = {
  legal_ingest: 'Số hóa Văn bản Luật',
  social_ingest: 'Thu thập MXH',
  vector_sync: 'Đồng bộ Qdrant / Neo4j',
  brief_generate: 'Tạo Bản tóm tắt (AI)',
};

function jobTypeLabel(type: string) { return TYPE_LABELS[type] || type; }
function jobDetails(p: Record<string, unknown>): string {
  return (p?.so_hieu as string) || (p?.ten as string) || (p?.platform as string) || (p?.url as string) || '—';
}
function errorText(err: unknown): string | null {
  if (!err) return null;
  if (typeof err === 'string') return err;
  try { return JSON.stringify(err); } catch { return String(err); }
}
function formatTime(iso?: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString('vi-VN');
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [summary, setSummary] = useState<JobsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(true);

  const fetchJobs = async () => {
    try {
      const data = await apiGet<JobsResponse>('/admin/jobs');
      setJobs(data.items ?? []);
      setSummary(data.summary ?? null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách job');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    if (!isPolling) return;
    const interval = setInterval(fetchJobs, 3000);
    return () => clearInterval(interval);
  }, [isPolling]);

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <HardDrives size={28} weight="fill" className="text-primary" /> Quản lý Tiến trình (Jobs)
          </h1>
          <p className="text-slate-500 text-sm mt-1">Giám sát các tác vụ chạy ngầm: số hóa luật, quét mạng xã hội, đồng bộ AI.</p>
        </div>
        <button
          onClick={() => setIsPolling(!isPolling)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors border ${isPolling ? 'bg-primary/10 border-primary/20 text-primary' : 'bg-surface border-border text-muted hover:bg-slate-50'}`}
        >
          <ArrowsClockwise size={16} className={isPolling ? 'animate-spin' : ''} />
          {isPolling ? 'Đang tự động cập nhật' : 'Tự động cập nhật: Tắt'}
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="bg-surface border border-border rounded-xl p-4">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Đang chạy</div>
            <div className="text-2xl font-black text-blue-600 mt-1">{summary.total_running}</div>
          </div>
          <div className="bg-surface border border-border rounded-xl p-4">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Hàng đợi</div>
            <div className="text-2xl font-black text-slate-600 mt-1">{summary.total_queued ?? 0}</div>
          </div>
          <div className="bg-surface border border-border rounded-xl p-4">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Cần duyệt</div>
            <div className="text-2xl font-black text-amber-600 mt-1">{summary.total_needs_review}</div>
          </div>
          <div className="bg-surface border border-border rounded-xl p-4">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Lỗi</div>
            <div className={`text-2xl font-black mt-1 ${summary.total_failed > 0 ? 'text-red-600' : 'text-emerald-600'}`}>{summary.total_failed}</div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2">
          <WarningCircle size={20} weight="fill" className="text-red-500 shrink-0" /> <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="py-20 flex justify-center"><Spinner size={32} className="animate-spin text-primary" /></div>
      ) : jobs.length === 0 && !error ? (
        <div className="bg-surface rounded-2xl border border-border p-12 text-center text-slate-500">Không có tiến trình nào.</div>
      ) : (
        <div className="space-y-4">
          {jobs.map((job) => {
            const config = getStatusConfig(job.status);
            const err = errorText(job.error);
            return (
              <div key={job.job_id} className="bg-surface border border-border rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600 shrink-0">
                      <FileText size={22} weight="fill" />
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-bold text-slate-900 text-base">{jobTypeLabel(job.type)}</h3>
                      <p className="text-xs text-slate-500 font-mono mt-0.5 truncate">ID: {job.job_id}</p>
                    </div>
                  </div>
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-bold shrink-0 ${config.bg} ${config.color}`}>
                    {config.icon}{config.label}
                  </div>
                </div>

                <div className="mt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-sm">
                  <div className="text-slate-600 truncate"><span className="font-medium">Đối tượng:</span> {jobDetails(job.payload)}</div>
                  <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 shrink-0">
                    <Clock size={14} /> {formatTime(job.created_at)}
                  </div>
                </div>

                {err && (
                  <div className="mt-3 p-3 bg-red-50 text-red-700 text-xs font-mono rounded-lg border border-red-100 overflow-x-auto">{err}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
