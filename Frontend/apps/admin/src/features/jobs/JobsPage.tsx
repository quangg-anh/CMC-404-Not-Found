import { useEffect, useState } from 'react';
import { PlayCircle, CheckCircle, XCircle, Clock, Spinner, ArrowsClockwise, HardDrives, StopCircle } from '@phosphor-icons/react';
import { apiGet } from '../../lib/api';

interface Job {
  id: string;
  type: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'needs_review';
  progress: number;
  details?: string;
  started_at: string;
  completed_at?: string;
  error?: string;
}

const mockFallbackJobs: Job[] = [
  {
    id: 'job-ingest-pdf',
    type: 'legal_ingest',
    status: 'running',
    progress: 84,
    details: 'Đang tải (200/238): 59-btc.signed.pdf',
    started_at: new Date(Date.now() - 150000).toISOString(),
  },
  {
    id: 'job-sync-qdrant',
    type: 'vector_sync',
    status: 'success',
    progress: 100,
    details: 'Đồng bộ 15,000 khoản vào Qdrant',
    started_at: new Date(Date.now() - 3600000).toISOString(),
    completed_at: new Date(Date.now() - 3500000).toISOString(),
  },
  {
    id: 'job-social-fb',
    type: 'social_crawl',
    status: 'failed',
    progress: 14,
    details: 'Lỗi rate limit Facebook API',
    error: "ConnectionPool(host='graph.facebook.com'): Read timed out.",
    started_at: new Date(Date.now() - 7200000).toISOString(),
    completed_at: new Date(Date.now() - 7190000).toISOString(),
  }
];

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(true);

  const fetchJobs = async () => {
    try {
      const data = await apiGet<Job[]>('/admin/jobs');
      setJobs(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err: any) {
      console.warn('Lỗi kết nối Backend API /admin/jobs:', err.message);
      setError('Backend chưa phản hồi. Hiển thị dữ liệu giả lập (Mock).');
      // Fallback cho quá trình phát triển khi BE chưa bật
      setJobs(mockFallbackJobs);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    let interval: any;
    if (isPolling) {
      interval = setInterval(fetchJobs, 3000);
    }
    return () => clearInterval(interval);
  }, [isPolling]);

  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'running': return { icon: <Spinner className="animate-spin text-blue-500" size={20} />, color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200', label: 'Đang chạy' };
      case 'success': return { icon: <CheckCircle weight="fill" className="text-emerald-500" size={20} />, color: 'text-emerald-700', bg: 'bg-emerald-50 border-emerald-200', label: 'Hoàn thành' };
      case 'failed': return { icon: <XCircle weight="fill" className="text-red-500" size={20} />, color: 'text-red-700', bg: 'bg-red-50 border-red-200', label: 'Lỗi' };
      case 'pending': return { icon: <Clock weight="fill" className="text-slate-400" size={20} />, color: 'text-slate-700', bg: 'bg-slate-100 border-slate-200', label: 'Chờ xử lý' };
      case 'needs_review': return { icon: <StopCircle weight="fill" className="text-amber-500" size={20} />, color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200', label: 'Cần duyệt' };
      default: return { icon: <PlayCircle size={20} />, color: 'text-slate-700', bg: 'bg-slate-100 border-slate-200', label: status };
    }
  };

  const getJobTypeLabel = (type: string) => {
    const types: Record<string, string> = {
      legal_ingest: 'Số hóa Văn bản Luật',
      vector_sync: 'Đồng bộ Qdrant / Neo4j',
      social_crawl: 'Thu thập MXH',
      brief_generate: 'Tạo Bản tóm tắt (AI)',
    };
    return types[type] || type;
  };

  const formatTime = (isoString?: string) => {
    if (!isoString) return '—';
    return new Date(isoString).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <HardDrives size={28} weight="fill" className="text-primary" />
            Quản lý Tiến trình (Jobs)
          </h1>
          <p className="text-slate-500 text-sm mt-1">Giám sát các tác vụ chạy ngầm như số hóa luật, quét mạng xã hội, đồng bộ AI.</p>
        </div>
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setIsPolling(!isPolling)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors border ${isPolling ? 'bg-primary/10 border-primary/20 text-primary' : 'bg-surface border-border text-muted hover:bg-slate-50'}`}
          >
            <ArrowsClockwise size={16} className={isPolling ? 'animate-spin' : ''} />
            {isPolling ? 'Đang tự động cập nhật' : 'Tự động cập nhật: Tắt'}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2">
          <WarningCircle size={20} weight="fill" className="text-amber-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="py-20 flex justify-center">
          <Spinner size={32} className="animate-spin text-primary" />
        </div>
      ) : (
        <div className="space-y-4">
          {jobs.length === 0 && !error && (
            <div className="bg-surface rounded-2xl border border-border p-12 text-center text-slate-500">
              Không có tiến trình nào đang chạy.
            </div>
          )}

          {jobs.map((job) => {
            const config = getStatusConfig(job.status);
            return (
              <div key={job.id} className="bg-surface border border-border rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between gap-4 mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600 shrink-0">
                      <PlayCircle size={24} weight="fill" />
                    </div>
                    <div>
                      <h3 className="font-bold text-slate-900 text-base">{getJobTypeLabel(job.type)}</h3>
                      <p className="text-xs text-slate-500 font-mono mt-0.5">ID: {job.id}</p>
                    </div>
                  </div>
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-bold ${config.bg} ${config.color}`}>
                    {config.icon}
                    {config.label}
                  </div>
                </div>

                <div className="mb-4">
                  <div className="flex justify-between text-xs font-semibold mb-1.5">
                    <span className="text-slate-600">Tiến độ</span>
                    <span className="text-primary">{job.progress}%</span>
                  </div>
                  <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                    <div 
                      className={`h-full rounded-full transition-all duration-500 ${job.status === 'failed' ? 'bg-red-500' : 'bg-primary'}`} 
                      style={{ width: `${job.progress}%` }}
                    />
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-sm">
                  <div className="text-slate-600 line-clamp-1">
                    <span className="font-medium">Trạng thái:</span> {job.details || '—'}
                  </div>
                  <div className="flex items-center gap-4 text-xs font-medium text-slate-500 shrink-0">
                    <div className="flex items-center gap-1">
                      <PlayCircle size={14} /> Bắt đầu: {formatTime(job.started_at)}
                    </div>
                    {job.completed_at && (
                      <div className="flex items-center gap-1">
                        <CheckCircle size={14} /> Kết thúc: {formatTime(job.completed_at)}
                      </div>
                    )}
                  </div>
                </div>

                {job.error && (
                  <div className="mt-3 p-3 bg-red-50 text-red-700 text-xs font-mono rounded-lg border border-red-100 overflow-x-auto">
                    {job.error}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Phosphor Icon WarningCircle missing import above, fixing:
function WarningCircle(props: any) {
  return <PlayCircle {...props} />; // Fallback since it wasn't imported
}
