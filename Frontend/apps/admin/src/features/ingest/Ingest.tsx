import { useEffect, useState } from 'react';
import { UploadSimple, FileText, Spinner, CheckCircle, Clock, WarningCircle, ArrowClockwise } from '@phosphor-icons/react';
import { apiGet, apiPost } from '../../lib/api';

interface IngestResponse {
  job_id: string;
  so_hieu: string;
  status: string;
  message: string;
}

interface JobItem {
  job_id: string;
  type: string;
  status: string;
  payload: Record<string, unknown>;
  error: unknown;
  created_at: string | null;
}

interface JobsResponse {
  items: JobItem[];
  total: number;
  summary: { total_running: number; total_failed: number; total_needs_review: number; health: string };
}

function statusBadge(status: string) {
  const map: Record<string, { cls: string; label: string; icon: React.ReactNode }> = {
    queued: { cls: 'bg-brand/10 text-brand', label: 'Trong hàng đợi', icon: <Clock size={14} /> },
    running: { cls: 'bg-blue-50 text-blue-600', label: 'Đang xử lý', icon: <Spinner size={14} className="animate-spin" /> },
    success: { cls: 'bg-emerald-50 text-emerald-600', label: 'Hoàn tất', icon: <CheckCircle size={14} weight="fill" /> },
    needs_review: { cls: 'bg-amber-50 text-amber-600', label: 'Cần review', icon: <WarningCircle size={14} weight="fill" /> },
    failed: { cls: 'bg-red-50 text-red-600', label: 'Lỗi', icon: <WarningCircle size={14} weight="fill" /> },
  };
  const c = map[status] ?? { cls: 'bg-slate-100 text-slate-500', label: status, icon: <Clock size={14} /> };
  return (
    <span className={`text-xs font-bold px-2.5 py-1 rounded flex items-center gap-1 ${c.cls}`}>
      {c.icon} {c.label}
    </span>
  );
}

export default function IngestPage() {
  const [soHieu, setSoHieu] = useState('');
  const [ten, setTen] = useState('');
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastJob, setLastJob] = useState<IngestResponse | null>(null);

  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);

  const loadJobs = () => {
    setJobsLoading(true);
    apiGet<JobsResponse>('/admin/jobs?type=legal_ingest')
      .then((data) => setJobs(data.items ?? []))
      .catch(() => setJobs([]))
      .finally(() => setJobsLoading(false));
  };

  useEffect(() => {
    loadJobs();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!soHieu.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiPost<IngestResponse>('/admin/ingest/legal', {
        so_hieu: soHieu.trim(),
        ten: ten.trim() || null,
        url_or_content: content.trim() || null,
      });
      setLastJob(res);
      setSoHieu('');
      setTen('');
      setContent('');
      loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi khi gửi văn bản');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto pb-20 animate-fade-in-up">
      <div className="mb-10">
        <h1 className="text-3xl font-black text-slate-900 tracking-tight mb-2">Số hóa Văn bản Pháp luật</h1>
        <p className="text-slate-500 font-medium">
          Đưa văn bản mới vào pipeline xử lý. Nhập số hiệu và nội dung/URL; hệ thống tạo job xử lý bất đồng bộ.
        </p>
      </div>

      <form onSubmit={submit} className="bg-white rounded-[24px] border border-slate-200 shadow-sm p-8 mb-10">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Số hiệu văn bản *</label>
            <input
              value={soHieu}
              onChange={(e) => setSoHieu(e.target.value)}
              placeholder="VD: 168/2024/NĐ-CP"
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium focus:outline-none focus:border-brand/40 focus:ring-2 focus:ring-brand/10 transition-all"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Tên văn bản</label>
            <input
              value={ten}
              onChange={(e) => setTen(e.target.value)}
              placeholder="VD: Nghị định xử phạt vi phạm giao thông…"
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium focus:outline-none focus:border-brand/40 focus:ring-2 focus:ring-brand/10 transition-all"
            />
          </div>
        </div>
        <div className="mb-6">
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Nội dung hoặc URL nguồn</label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={5}
            placeholder="Dán nội dung văn bản hoặc URL nguồn chính thống…"
            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium focus:outline-none focus:border-brand/40 focus:ring-2 focus:ring-brand/10 transition-all resize-y"
          />
        </div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-400 font-medium flex items-center gap-1.5">
            <UploadSimple size={16} /> Tải file PDF/DOCX sẽ hỗ trợ khi endpoint upload sẵn sàng.
          </p>
          <button
            type="submit"
            disabled={submitting || !soHieu.trim()}
            className="bg-slate-900 text-white font-bold px-8 py-3 rounded-xl hover:bg-brand transition-colors shadow-lg shadow-slate-900/10 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? <Spinner size={18} className="animate-spin" /> : <UploadSimple size={18} weight="bold" />}
            {submitting ? 'Đang gửi…' : 'Đưa vào pipeline'}
          </button>
        </div>

        {error && <div className="mt-4 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-semibold">{error}</div>}
        {lastJob && (
          <div className="mt-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl px-4 py-3 text-sm font-semibold flex items-center gap-2">
            <CheckCircle size={18} weight="fill" /> Đã tạo job <code className="bg-white px-1.5 py-0.5 rounded text-emerald-700">{lastJob.job_id}</code> — {lastJob.message}
          </div>
        )}
      </form>

      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-slate-900">Job số hóa gần đây</h3>
        <button onClick={loadJobs} className="text-sm font-bold text-slate-500 hover:text-brand flex items-center gap-1.5 transition-colors">
          <ArrowClockwise size={16} /> Làm mới
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm divide-y divide-slate-100">
        {jobsLoading ? (
          <div className="p-8 text-center text-slate-400 font-semibold flex items-center justify-center gap-2">
            <Spinner size={18} className="animate-spin" /> Đang tải danh sách job…
          </div>
        ) : jobs.length === 0 ? (
          <div className="p-8 text-center text-slate-400 font-semibold">Chưa có job số hóa nào.</div>
        ) : (
          jobs.map((job) => (
            <div key={job.job_id} className="p-5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-500 flex items-center justify-center shrink-0">
                  <FileText size={20} weight="fill" />
                </div>
                <div className="min-w-0">
                  <div className="font-bold text-slate-800 text-sm truncate">
                    {(job.payload?.so_hieu as string) || (job.payload?.ten as string) || job.job_id}
                  </div>
                  <div className="text-xs text-slate-400 font-medium">{job.created_at ?? '—'}</div>
                </div>
              </div>
              {statusBadge(job.status)}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
