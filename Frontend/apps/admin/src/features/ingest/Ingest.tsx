import { useEffect, useRef, useState } from 'react';
import { UploadSimple, FileText, Spinner, CheckCircle, Clock, WarningCircle, ArrowClockwise, Paperclip, X, Trash, MagnifyingGlass } from '@phosphor-icons/react';
import { apiDelete, apiGet, apiPost, apiUpload } from '../../lib/api';

interface IngestResponse {
  job_id: string;
  so_hieu: string;
  status: string;
  message: string;
  vb_id?: string;
  dieu_count?: number;
  khoan_count?: number;
  indexed_count?: number;
  needs_review?: boolean;
}

interface UploadResponse {
  file_id: string;
  storage_key: string;
  filename: string;
  van_ban_id: string;
  size_bytes: number;
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

interface VanBanItem { vb_id?: string; id?: string; so_hieu?: string; ten?: string; tieu_de?: string; source_filename?: string; ngay_ban_hanh?: string | null }
interface VanBanResponse { items: VanBanItem[]; total: number }

function statusBadge(status: string) {
  const map: Record<string, { cls: string; label: string; icon: React.ReactNode }> = {
    queued: { cls: 'bg-brand/10 text-brand', label: 'Trong hàng đợi', icon: <Clock size={14} /> },
    running: { cls: 'bg-blue-50 text-blue-600', label: 'Đang xử lý', icon: <Spinner size={14} className="animate-spin" /> },
    success: { cls: 'bg-emerald-50 text-emerald-600', label: 'Hoàn tất', icon: <CheckCircle size={14} weight="fill" /> },
    needs_review: { cls: 'bg-amber-50 text-amber-600', label: 'Cần review', icon: <WarningCircle size={14} weight="fill" /> },
    error: { cls: 'bg-red-50 text-red-600', label: 'Lỗi', icon: <WarningCircle size={14} weight="fill" /> },
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
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [stage, setStage] = useState<'idle' | 'uploading' | 'ingesting'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [lastJob, setLastJob] = useState<IngestResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [documents, setDocuments] = useState<VanBanItem[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const loadJobs = () => {
    setJobsLoading(true);
    apiGet<JobsResponse>('/admin/jobs?type=legal_ingest')
      .then((data) => setJobs(data.items ?? []))
      .catch(() => setJobs([]))
      .finally(() => setJobsLoading(false));
  };

  const loadDocuments = () => {
    setDocumentsLoading(true);
    apiGet<VanBanResponse>('/admin/legal/van-ban')
      .then((data) => setDocuments(data.items ?? []))
      .catch(() => setDocuments([]))
      .finally(() => setDocumentsLoading(false));
  };

  useEffect(() => {
    loadJobs();
    loadDocuments();
  }, []);

  const deleteDocument = async (doc: VanBanItem) => {
    const id = doc.vb_id || doc.id || doc.so_hieu;
    if (!id || deletingId) return;
    const label = doc.so_hieu || doc.tieu_de || doc.ten || id;
    if (!window.confirm(`Xóa văn bản "${label}" khỏi Neo4j/Qdrant? Hành động này không hoàn tác.`)) return;
    setDeletingId(id);
    setError(null);
    try {
      await apiDelete(`/admin/legal/van-ban/${encodeURIComponent(id)}`);
      loadDocuments();
      loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi khi xóa văn bản');
    } finally {
      setDeletingId(null);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!soHieu.trim() || submitting) return;
    if (!content.trim() && !file) {
      setError('Cần dán nội dung/URL hoặc chọn file để số hóa.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      // Step 1: if a file was chosen, upload it to MinIO first and collect its file_id.
      let fileIds: string[] = [];
      if (file) {
        setStage('uploading');
        const fd = new FormData();
        fd.append('file', file);
        fd.append('so_hieu', soHieu.trim());
        fd.append('visibility', 'public');
        const up = await apiUpload<UploadResponse>('/admin/legal/upload', fd);
        fileIds = [up.file_id];
      }
      // Step 2: run digitization (parse -> Neo4j -> Qdrant). Backend reads the file back from MinIO.
      setStage('ingesting');
      const res = await apiPost<IngestResponse>('/admin/ingest/legal', {
        so_hieu: soHieu.trim(),
        ten: ten.trim() || null,
        url_or_content: content.trim() || null,
        file_ids: fileIds,
      });
      setLastJob(res);
      setSoHieu('');
      setTen('');
      setContent('');
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadJobs();
      loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi khi gửi văn bản');
    } finally {
      setSubmitting(false);
      setStage('idle');
    }
  };

  const filteredDocs = documents.filter(doc => {
    const q = searchQuery.toLowerCase();
    const soHieu = (doc.so_hieu || '').toLowerCase();
    const ten = (doc.ten || '').toLowerCase();
    const tieuDe = (doc.tieu_de || '').toLowerCase();
    return soHieu.includes(q) || ten.includes(q) || tieuDe.includes(q);
  });

  return (
    <div className="max-w-4xl mx-auto pb-20 animate-fade-in-up">
      <div className="mb-10">
        <h1 className="text-3xl font-black text-slate-900 tracking-tight mb-2">Số hóa Văn bản Pháp luật</h1>
        <p className="text-slate-500 font-medium">
          Đưa văn bản mới vào hệ thống. Nhập số hiệu rồi dán nội dung/URL hoặc tải file (PDF/DOCX/TXT); hệ thống lưu file gốc vào MinIO, bóc tách Điều/Khoản vào đồ thị tri thức và index vector để AI truy hồi được ngay.
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
        <div className="mb-6">
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">File văn bản gốc (PDF / DOCX / TXT)</label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.html,.htm,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="hidden"
            id="legal-file-input"
          />
          {file ? (
            <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-700 min-w-0">
                <Paperclip size={16} className="shrink-0" />
                <span className="truncate">{file.name}</span>
                <span className="text-slate-400 font-medium shrink-0">({(file.size / 1024).toFixed(0)} KB)</span>
              </span>
              <button
                type="button"
                onClick={() => {
                  setFile(null);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }}
                className="text-slate-400 hover:text-red-500 transition-colors shrink-0"
                aria-label="Bỏ file"
              >
                <X size={18} weight="bold" />
              </button>
            </div>
          ) : (
            <label
              htmlFor="legal-file-input"
              className="flex items-center gap-2 cursor-pointer bg-slate-50 border border-dashed border-slate-300 rounded-xl px-4 py-3 text-sm font-semibold text-slate-500 hover:border-brand/40 hover:text-brand transition-all"
            >
              <Paperclip size={16} /> Chọn file để tải lên MinIO và số hóa…
            </label>
          )}
        </div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-400 font-medium flex items-center gap-1.5">
            <UploadSimple size={16} /> Dán nội dung/URL hoặc tải file — hệ thống tự bóc tách Điều/Khoản.
          </p>
          <button
            type="submit"
            disabled={submitting || !soHieu.trim()}
            className="bg-slate-900 text-white font-bold px-8 py-3 rounded-xl hover:bg-brand transition-colors shadow-lg shadow-slate-900/10 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? <Spinner size={18} className="animate-spin" /> : <UploadSimple size={18} weight="bold" />}
            {stage === 'uploading' ? 'Đang tải file…' : stage === 'ingesting' ? 'Đang số hóa…' : 'Đưa vào pipeline'}
          </button>
        </div>

        {error && <div className="mt-4 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-semibold">{error}</div>}
        {lastJob && (
          <div
            className={`mt-4 border rounded-xl px-4 py-3 text-sm font-semibold flex items-center gap-2 ${
              lastJob.status === 'success'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : lastJob.status === 'needs_review'
                  ? 'bg-amber-50 border-amber-200 text-amber-800'
                  : 'bg-brand/5 border-brand/20 text-slate-700'
            }`}
          >
            {lastJob.status === 'success' ? <CheckCircle size={18} weight="fill" /> : <Clock size={18} />}
            <span>
              Job <code className="bg-white px-1.5 py-0.5 rounded">{lastJob.job_id.slice(0, 8)}</code> — {lastJob.message}
              {typeof lastJob.dieu_count === 'number' && lastJob.dieu_count > 0 && (
                <span className="ml-1 text-slate-500">
                  ({lastJob.dieu_count} Điều · {lastJob.khoan_count} Khoản
                  {typeof lastJob.indexed_count === 'number' ? ` · ${lastJob.indexed_count} vector` : ''})
                </span>
              )}
            </span>
          </div>
        )}
      </form>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <h3 className="text-lg font-bold text-slate-900">Văn bản đã số hóa <span className="text-slate-400 text-sm font-medium ml-1">({filteredDocs.length})</span></h3>
        <div className="flex items-center gap-3">
          <div className="relative">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              type="text" 
              placeholder="Tìm số hiệu, tên..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand w-full sm:w-64 transition-all"
            />
          </div>
          <button onClick={loadDocuments} className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm font-bold text-slate-600 hover:text-brand hover:border-brand/30 flex items-center gap-1.5 transition-all shadow-sm shrink-0">
            <ArrowClockwise size={16} /> Làm mới
          </button>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden mb-10">
        {documentsLoading ? (
          <div className="p-8 text-center text-slate-400 font-semibold flex items-center justify-center gap-2">
            <Spinner size={18} className="animate-spin" /> Đang tải danh sách văn bản…
          </div>
        ) : filteredDocs.length === 0 ? (
          <div className="p-8 text-center text-slate-400 font-medium text-sm">Không tìm thấy văn bản phù hợp.</div>
        ) : (
          <div className="max-h-[400px] overflow-y-auto divide-y divide-slate-100">
            {filteredDocs.map((doc) => {
              const id = doc.vb_id || doc.id || doc.so_hieu || '';
              const title = doc.tieu_de || doc.ten || doc.so_hieu || id;
              return (
                <div key={id} className="p-4 hover:bg-slate-50 transition-colors flex items-center justify-between gap-4 group">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-lg bg-brand/5 text-brand flex items-center justify-center shrink-0">
                      <FileText size={18} weight="fill" />
                    </div>
                    <div className="min-w-0">
                      <div className="font-bold text-slate-800 text-sm truncate group-hover:text-brand transition-colors">{title}</div>
                      <div className="text-xs text-slate-400 font-medium truncate mt-0.5">
                        <span className="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded text-[10px] uppercase font-bold mr-2">{doc.so_hieu || 'N/A'}</span>
                        {doc.source_filename || id}{doc.ngay_ban_hanh ? ` · ${doc.ngay_ban_hanh}` : ''}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => deleteDocument(doc)}
                    disabled={deletingId === id}
                    className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 flex items-center transition-all disabled:opacity-50 shrink-0 opacity-100 sm:opacity-50 sm:group-hover:opacity-100"
                    title="Xóa văn bản"
                  >
                    {deletingId === id ? <Spinner size={16} className="animate-spin" /> : <Trash size={18} />}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

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
