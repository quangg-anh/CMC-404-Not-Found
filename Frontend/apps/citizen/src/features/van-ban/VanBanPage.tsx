import { useEffect, useState } from 'react';
import { Clock, ShieldCheck, TreeStructure, BookmarkSimple, Spinner, FileText, DownloadSimple, FilePdf } from '@phosphor-icons/react';
import { apiGet, fileUrl } from '../../lib/api';
import { CitizenHeader } from '../../components/CitizenChrome';
import { Atmosphere } from '../../components/Atmosphere';

interface Khoan {
  khoan_id?: string;
  so_khoan?: string | number;
  noi_dung?: string;
  dieu?: string;
}

interface VanBanFile {
  file_id?: string;
  id?: string;
  filename?: string;
  ten_file?: string;
  size_bytes?: number;
  kich_thuoc?: number;
}
interface FilesResponse { files: VanBanFile[]; total: number }

function fileId(f: VanBanFile): string { return f.file_id ?? f.id ?? ''; }
function fileName(f: VanBanFile): string { return f.filename ?? f.ten_file ?? fileId(f) ?? 'tài liệu'; }
function fileSizeMB(f: VanBanFile): string {
  const b = f.size_bytes ?? f.kich_thuoc ?? 0;
  return b > 0 ? `${(b / 1024 / 1024).toFixed(2)} MB` : '';
}

interface VanBan {
  vb_id?: string;
  so_hieu?: string;
  ten?: string;
  ngay_ban_hanh?: string;
  co_quan_ban_hanh?: string;
  trang_thai?: string;
  tom_tat?: string;
  tree?: Khoan[];
  files?: VanBanFile[];
}

interface VanBanListResponse {
  items: VanBan[];
  total: number;
}

function docId(v: VanBan): string {
  return v.vb_id ?? v.so_hieu ?? '';
}

export default function VanBanPage() {
  const [docs, setDocs] = useState<VanBan[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<VanBan | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<VanBanListResponse>('/citizen/legal/van-ban')
      .then((data) => {
        const items = data.items ?? [];
        setDocs(items);
        if (items.length > 0) setSelectedId(docId(items[0]));
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Lỗi tải danh sách văn bản'))
      .finally(() => setListLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    const enc = encodeURIComponent(selectedId);
    Promise.all([
      apiGet<VanBan>(`/citizen/legal/van-ban/${enc}`),
      apiGet<FilesResponse>(`/citizen/legal/van-ban/${enc}/files`).catch(() => ({ files: [], total: 0 })),
    ])
      .then(([doc, filesRes]) => setDetail({ ...doc, files: filesRes.files ?? [] }))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  return (
    <div className="relative flex min-h-screen flex-col bg-background font-sans">
      <Atmosphere tone="section" />
      <CitizenHeader />

      <main id="main" className="relative mx-auto flex w-full max-w-7xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6 md:flex-row">
        {/* Left: document list */}
        <aside className="w-full shrink-0 md:w-1/3 lg:w-1/4">
          <div className="sticky top-24 rounded-[28px] border-2 border-border bg-white p-5 shadow-soft">
            <h3 className="mb-4 flex items-center gap-2 border-b-2 border-border pb-4 font-display text-xl font-bold text-primary">
              <TreeStructure size={24} className="text-civic" aria-hidden /> Văn bản công khai
            </h3>

            {listLoading ? (
              <div className="py-8 text-center text-slate-400 text-sm font-semibold flex items-center justify-center gap-2">
                <Spinner size={16} className="animate-spin" /> Đang tải…
              </div>
            ) : docs.length === 0 ? (
              <p className="py-8 text-center text-slate-400 text-sm font-medium">Chưa có văn bản công khai.</p>
            ) : (
              <nav className="space-y-1">
                {docs.map((d) => {
                  const id = docId(d);
                  const active = id === selectedId;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setSelectedId(id)}
                      className={`w-full rounded-2xl border-2 px-4 py-3 text-left transition duration-200 ${
                        active
                          ? 'border-civic bg-civicSoft text-civicDark'
                          : 'border-transparent text-primary hover:border-border hover:bg-background'
                      }`}
                    >
                      <div className="mb-1 text-base font-extrabold">{d.so_hieu ?? id}</div>
                      <div className="line-clamp-2 text-base text-muted">{d.ten ?? 'Văn bản pháp luật'}</div>
                    </button>
                  );
                })}
              </nav>
            )}
          </div>
        </aside>

        {/* Main content */}
        <div className="flex-1 max-w-3xl">
          {error ? (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl px-6 py-5 text-sm font-semibold">{error}</div>
          ) : detailLoading ? (
            <div className="bg-white rounded-3xl p-16 border border-slate-200 shadow-sm text-center text-slate-400 font-semibold flex items-center justify-center gap-2">
              <Spinner size={20} className="animate-spin" /> Đang tải nội dung văn bản…
            </div>
          ) : !detail ? (
            <div className="bg-white rounded-3xl p-16 border border-slate-200 shadow-sm text-center">
              <FileText size={40} className="text-slate-300 mx-auto mb-4" weight="fill" />
              <p className="text-slate-500 font-semibold">Chọn một văn bản để xem nội dung.</p>
            </div>
          ) : (
            <>
              <div className="bg-white rounded-3xl p-8 border border-slate-200 shadow-sm mb-6">
                <div className="flex flex-wrap items-center gap-3 mb-4">
                  {detail.so_hieu && (
                    <span className="inline-flex items-center px-3 py-1 bg-red-50 text-brand text-xs font-bold rounded-lg uppercase tracking-wider border border-red-100">
                      {detail.so_hieu}
                    </span>
                  )}
                  {detail.trang_thai && (
                    <span className="inline-flex items-center px-3 py-1 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-lg uppercase tracking-wider border border-emerald-100">
                      <ShieldCheck size={14} className="mr-1" /> {detail.trang_thai}
                    </span>
                  )}
                </div>

                <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 leading-tight mb-4">
                  {detail.ten ?? 'Văn bản pháp luật'}
                </h1>

                <div className="flex flex-wrap gap-6 text-sm text-slate-500 font-medium mb-6 pb-6 border-b border-slate-100">
                  {detail.ngay_ban_hanh && <div className="flex items-center gap-1.5"><Clock size={16} /> Ban hành: {detail.ngay_ban_hanh}</div>}
                  {detail.co_quan_ban_hanh && <div className="flex items-center gap-1.5"><BookmarkSimple size={16} /> {detail.co_quan_ban_hanh}</div>}
                </div>

                {detail.tom_tat && (
                  <div className="bg-slate-50 rounded-xl p-5 border border-slate-100">
                    <h4 className="font-bold text-slate-800 mb-2">Tóm tắt văn bản</h4>
                    <p className="text-slate-600 leading-relaxed text-sm">{detail.tom_tat}</p>
                  </div>
                )}
              </div>

              <div className="bg-white rounded-3xl p-8 sm:p-10 border border-slate-200 shadow-[0_8px_30px_rgb(0,0,0,0.02)]">
                <article className="prose prose-slate max-w-none">
                  {detail.tree && detail.tree.length > 0 ? (
                    detail.tree.map((k, idx) => (
                      <div key={k.khoan_id ?? idx} className="mb-6">
                        {(k.dieu || k.so_khoan) && (
                          <h3 className="text-lg font-bold text-slate-900 mb-2">
                            {k.dieu ?? ''}{k.so_khoan ? ` — Khoản ${k.so_khoan}` : ''}
                          </h3>
                        )}
                        <p className="font-medium text-slate-700 leading-relaxed">{k.noi_dung}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-slate-400 italic">Nội dung chi tiết Điều/Khoản chưa được số hóa cho văn bản này.</p>
                  )}
                </article>
              </div>

              {detail.files && detail.files.length > 0 && (
                <div className="bg-white rounded-3xl p-8 sm:p-10 border border-slate-200 shadow-[0_8px_30px_rgb(0,0,0,0.02)] mt-6">
                  <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2 mb-4">
                    <FilePdf size={24} className="text-red-500" weight="fill" /> Tài liệu đính kèm (Bản gốc)
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {detail.files.map(f => (
                      <div key={fileId(f)} className="flex items-center justify-between p-4 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 transition-colors">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-10 h-10 rounded-lg bg-red-100 text-red-600 flex items-center justify-center shrink-0">
                            <FilePdf size={20} weight="fill" />
                          </div>
                          <div className="min-w-0">
                            <p className="font-bold text-slate-800 text-sm truncate" title={fileName(f)}>{fileName(f)}</p>
                            {fileSizeMB(f) && <p className="text-xs text-slate-500 mt-0.5">{fileSizeMB(f)}</p>}
                          </div>
                        </div>
                        <a 
                          href={fileUrl(fileId(f))} 
                          target="_blank" rel="noopener noreferrer"
                          className="shrink-0 w-8 h-8 flex items-center justify-center rounded-full bg-white border border-slate-300 text-slate-600 hover:text-brand hover:border-brand shadow-sm transition-all"
                          title="Tải xuống"
                        >
                          <DownloadSimple size={16} weight="bold" />
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
