import { useEffect, useState } from 'react';
import { ArrowLeft, BookOpen, Clock, ShieldCheck, TreeStructure, BookmarkSimple, Spinner, FileText } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { apiGet } from '../../lib/api';

interface Khoan {
  khoan_id?: string;
  so_khoan?: string | number;
  noi_dung?: string;
  dieu?: string;
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
    apiGet<VanBan>(`/citizen/legal/van-ban/${encodeURIComponent(selectedId)}`)
      .then((data) => setDetail(data))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-slate-500 hover:text-brand font-semibold text-sm transition-colors">
            <ArrowLeft size={16} weight="bold" /> Quay lại Trang chủ
          </Link>
          <div className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <BookOpen size={18} className="text-brand" weight="fill" />
            Tra cứu Văn bản
          </div>
          <div className="w-24"></div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex flex-col md:flex-row gap-8">
        {/* Left: document list */}
        <aside className="w-full md:w-1/3 lg:w-1/4 shrink-0">
          <div className="bg-white rounded-2xl border border-slate-200 p-5 sticky top-20 shadow-[0_2px_10px_rgb(0,0,0,0.02)]">
            <h3 className="font-bold text-slate-900 flex items-center gap-2 mb-4 pb-4 border-b border-slate-100">
              <TreeStructure size={20} className="text-brand" /> Văn bản công khai
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
                      onClick={() => setSelectedId(id)}
                      className={`w-full text-left py-2.5 px-3 rounded-lg text-sm font-medium transition-colors ${
                        active ? 'bg-brand/5 text-brand border border-brand/10 font-semibold' : 'text-slate-600 hover:bg-slate-50 border border-transparent'
                      }`}
                    >
                      <div className="font-bold text-xs uppercase tracking-wide mb-0.5">{d.so_hieu ?? id}</div>
                      <div className="line-clamp-2 text-slate-500">{d.ten ?? 'Văn bản pháp luật'}</div>
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
            </>
          )}
        </div>
      </main>
    </div>
  );
}
