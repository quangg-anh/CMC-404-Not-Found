import { useEffect, useState } from 'react';
import {
  Article, Plus, FloppyDisk, UploadSimple, CheckCircle, Clock, Archive,
  FileText, WarningCircle, Link as LinkIcon, PenNib, Spinner, ArrowClockwise,
} from '@phosphor-icons/react';
import { apiGet, apiPatch, apiPost } from '../../../lib/api';

interface Brief {
  id: string;
  tieu_de: string;
  media_type: string;
  status: string;
  citations: Array<Record<string, any>>;
  created_at?: string;
}
interface ListResp { items: Brief[]; total: number }
interface SyncNewsResp { created_count?: number; skipped?: number; items_count?: number }

const MEDIA_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'article', label: 'Bài viết' },
  { value: 'qa', label: 'Hỏi–Đáp' },
  { value: 'infographic', label: 'Infographic' },
  { value: 'video_script', label: 'Kịch bản video' },
];

function statusBadge(status: string) {
  switch (status) {
    case 'published': return <span className="bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded text-xs font-bold border border-emerald-200">Đã ban hành</span>;
    case 'review': return <span className="bg-amber-50 text-amber-700 px-2 py-0.5 rounded text-xs font-bold border border-amber-200">Chờ duyệt</span>;
    case 'archived': return <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded text-xs font-bold border border-slate-200">Lưu trữ</span>;
    default: return <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded text-xs font-bold border border-blue-200">Bản nháp</span>;
  }
}
function citationText(c: Record<string, any>): string {
  return c.text ?? c.quote ?? [c.van_ban, c.dieu].filter(Boolean).join(' — ') ?? JSON.stringify(c);
}
function citationId(c: Record<string, any>, i: number): string {
  return c.id ?? c.khoan_id ?? `cit-${i}`;
}

export default function BriefsPage() {
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [active, setActive] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editMedia, setEditMedia] = useState('article');

  const select = (b: Brief) => {
    setActive(b);
    setEditTitle(b.tieu_de ?? '');
    // Map stored enum back to a business label (best effort).
    const alias = b.media_type === 'image' ? 'infographic' : b.media_type === 'video' ? 'video_script' : 'article';
    setEditMedia(alias);
  };

  const load = (keepId?: string) => {
    setLoading(true);
    apiGet<ListResp>('/admin/briefs')
      .then((d) => {
        const list = d.items ?? [];
        setBriefs(list);
        const pick = keepId ? list.find((x) => x.id === keepId) : list[0];
        if (pick) select(pick); else setActive(null);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Lỗi tải danh sách bản tin'))
      .finally(() => setLoading(false));
  };
  useEffect(() => load(), []);

  const generate = async () => {
    setSaving(true); setError(null); setNotice(null);
    try {
      const created = await apiPost<Brief>('/admin/briefs/generate', {
        tieu_de: 'Bản tin mới', noi_dung: '', citations: [], media_types: ['article'],
      });
      load(created.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi tạo bản tin');
    } finally { setSaving(false); }
  };

  const syncNews = async () => {
    setSaving(true); setError(null); setNotice(null);
    try {
      const data = await apiPost<SyncNewsResp>('/admin/briefs/sync-news', { limit_per_topic: 5 });
      setNotice(`Đã cập nhật tin phapluat.gov.vn: thêm ${data.created_count ?? 0}, bỏ qua ${data.skipped ?? 0}.`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi cập nhật tin pháp luật');
    } finally { setSaving(false); }
  };

  const save = async () => {
    if (!active) return;
    setSaving(true); setError(null); setNotice(null);
    try {
      const updated = await apiPatch<Brief>(`/admin/briefs/${active.id}`, { tieu_de: editTitle, media_types: [editMedia] });
      setBriefs((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
      select(updated);
      setNotice('Đã lưu bản nháp.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu bản tin');
    } finally { setSaving(false); }
  };

  const publish = async () => {
    if (!active) return;
    setSaving(true); setError(null); setNotice(null);
    try {
      const data = await apiPost<Brief>(`/admin/briefs/${active.id}/publish`, {});
      setBriefs((prev) => prev.map((b) => (b.id === data.id ? { ...b, ...data } : b)));
      select({ ...active, ...data });
      setNotice('Đã ban hành ra Cổng Người dân.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'PublishGate từ chối — kiểm tra trích dẫn pháp lý.');
    } finally { setSaving(false); }
  };

  const archive = async () => {
    if (!active) return;
    setSaving(true); setError(null); setNotice(null);
    try {
      const data = await apiPost<Brief>(`/admin/briefs/${active.id}/archive`, {});
      setBriefs((prev) => prev.map((b) => (b.id === data.id ? { ...b, ...data } : b)));
      select({ ...active, ...data });
      setNotice('Đã lưu trữ bản tin.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu trữ');
    } finally { setSaving(false); }
  };

  return (
    <div className="h-[calc(100vh-80px)] flex flex-col space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Article size={28} weight="fill" className="text-primary" /> Biên tập Bản tin (Briefs)
          </h1>
          <p className="text-slate-500 text-sm mt-1">Duyệt và biên tập bản tóm tắt pháp lý do AI đề xuất trước khi ban hành ra Cổng Người dân.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={syncNews} disabled={saving} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 shadow-sm transition-colors disabled:opacity-50">
            <ArrowClockwise size={16} weight="bold" /> Cập nhật tin pháp luật
          </button>
          <button onClick={generate} disabled={saving} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold bg-primary text-white hover:bg-primary-dark shadow-sm transition-colors disabled:opacity-50">
            <Plus size={16} weight="bold" /> Tạo bản tin
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2 shrink-0">
          <WarningCircle size={20} weight="fill" className="text-red-500 shrink-0" /> <span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2 shrink-0">
          <CheckCircle size={20} weight="fill" className="text-emerald-500 shrink-0" /> <span>{notice}</span>
        </div>
      )}

      <div className="flex-1 flex gap-6 overflow-hidden pb-4">
        {/* List */}
        <div className="w-[340px] flex flex-col bg-surface border border-border rounded-2xl overflow-hidden shadow-sm shrink-0">
          <div className="p-4 border-b border-border bg-slate-50 flex items-center justify-between">
            <h2 className="font-bold text-slate-700 text-sm">Danh sách Bản tin</h2>
            <button onClick={() => load(active?.id)} className="text-slate-400 hover:text-primary transition-colors"><ArrowClockwise size={16} /></button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loading ? (
              <div className="p-4 text-center text-slate-400 text-sm">Đang tải…</div>
            ) : briefs.length === 0 ? (
              <div className="p-6 text-center text-slate-400 text-sm">Chưa có bản tin nào.<br />Bấm “Tạo bản tin”.</div>
            ) : (
              briefs.map((b) => (
                <button key={b.id} onClick={() => select(b)} className={`w-full text-left p-3 rounded-xl transition-all border ${active?.id === b.id ? 'bg-primary/5 border-primary/20 shadow-sm' : 'bg-transparent border-transparent hover:bg-slate-50'}`}>
                  <div className="flex items-start justify-between mb-1 gap-2">
                    <span className="text-xs font-mono text-slate-400 truncate">{b.id.slice(0, 8)}</span>
                    {statusBadge(b.status)}
                  </div>
                  <h3 className={`text-sm font-bold line-clamp-2 leading-snug ${active?.id === b.id ? 'text-primary' : 'text-slate-700'}`}>{b.tieu_de}</h3>
                  {b.created_at && <p className="text-xs text-slate-500 mt-1 flex items-center gap-1"><Clock size={12} /> {new Date(b.created_at).toLocaleDateString('vi-VN')}</p>}
                </button>
              ))
            )}
          </div>
        </div>

        {/* Editor */}
        <div className="flex-1 flex flex-col bg-surface border border-border rounded-2xl overflow-hidden shadow-sm">
          {active ? (
            <>
              <div className="p-4 border-b border-border bg-slate-50 flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-slate-500 flex items-center gap-2"><PenNib size={18} /> Chỉnh sửa</span>
                  {statusBadge(active.status)}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={save} disabled={saving} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50">
                    {saving ? <Spinner size={16} className="animate-spin" /> : <FloppyDisk size={16} />} Lưu
                  </button>
                  <button onClick={archive} disabled={saving || active.status === 'archived'} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-slate-100 border border-slate-200 text-slate-600 hover:bg-slate-200 transition-colors disabled:opacity-40">
                    <Archive size={16} /> Lưu trữ
                  </button>
                  {active.status !== 'published' && (
                    <button onClick={publish} disabled={saving} className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-bold bg-primary text-white hover:bg-primary-dark transition-colors shadow-sm disabled:opacity-50">
                      <UploadSimple size={16} weight="bold" /> Ban hành
                    </button>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Tiêu đề bản tin</label>
                  <input type="text" value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50/50 text-slate-900 font-bold text-lg focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    placeholder="Nhập tiêu đề…" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Định dạng nội dung</label>
                  <select value={editMedia} onChange={(e) => setEditMedia(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50/50 text-slate-800 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all">
                    {MEDIA_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-1.5"><LinkIcon size={16} /> Căn cứ pháp lý đính kèm</label>
                  {(!active.citations || active.citations.length === 0) ? (
                    <div className="p-4 border border-dashed border-slate-300 rounded-xl text-center text-sm text-slate-500">
                      Chưa có căn cứ pháp lý. Bản tin cần trích dẫn hợp lệ mới ban hành được (PublishGate).
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {active.citations.map((c, i) => (
                        <div key={citationId(c, i)} className="flex items-center gap-3 p-3 bg-blue-50/50 border border-blue-100 rounded-xl">
                          <FileText size={20} className="text-blue-500 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <h4 className="text-sm font-bold text-blue-900 truncate">{citationText(c)}</h4>
                            {(c.khoan_id ?? c.id) && <p className="text-xs text-blue-600 font-mono mt-0.5 truncate">ID: {c.khoan_id ?? c.id}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">Chọn một bản tin để biên tập, hoặc tạo mới.</div>
          )}
        </div>
      </div>
    </div>
  );
}
