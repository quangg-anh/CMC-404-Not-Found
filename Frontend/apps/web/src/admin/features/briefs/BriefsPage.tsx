import { useEffect, useState } from 'react';
import {
  Article, Plus, FloppyDisk, UploadSimple, CheckCircle, Clock, Archive,
  FileText, WarningCircle, Link as LinkIcon, PenNib, Spinner, ArrowClockwise,
  Trash, MagnifyingGlass, X,
} from '@phosphor-icons/react';
import { apiDelete, apiGet, apiPatch, apiPost } from '../../../lib/api';

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
interface VanBanHit {
  vb_id?: string;
  so_hieu?: string;
  ten?: string;
  id?: string;
}
interface KhoanHit {
  khoan_id?: string;
  id?: string;
  so_khoan?: string;
  dieu?: string;
  noi_dung?: string;
  tieu_de?: string;
}

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
  return c.text ?? c.quote ?? [c.van_ban, c.dieu].filter(Boolean).join(' — ') || 'Căn cứ đã đính kèm';
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
  const [editCitations, setEditCitations] = useState<Array<Record<string, any>>>([]);
  const [searchQ, setSearchQ] = useState('');
  const [searching, setSearching] = useState(false);
  const [docHits, setDocHits] = useState<VanBanHit[]>([]);
  const [khoanHits, setKhoanHits] = useState<KhoanHit[]>([]);
  const [pickedDoc, setPickedDoc] = useState<string | null>(null);

  const select = (b: Brief) => {
    setActive(b);
    setEditTitle(b.tieu_de ?? '');
    const alias = b.media_type === 'image' ? 'infographic' : b.media_type === 'video' ? 'video_script' : 'article';
    setEditMedia(alias);
    setEditCitations(Array.isArray(b.citations) ? [...b.citations] : []);
    setSearchQ('');
    setDocHits([]);
    setKhoanHits([]);
    setPickedDoc(null);
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
      const updated = await apiPatch<Brief>(`/admin/briefs/${active.id}`, {
        tieu_de: editTitle,
        media_types: [editMedia],
        citations: editCitations,
      });
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
      // Persist citations first so publish uses the latest editor state.
      await apiPatch<Brief>(`/admin/briefs/${active.id}`, {
        tieu_de: editTitle,
        media_types: [editMedia],
        citations: editCitations,
      });
      const data = await apiPost<Brief>(`/admin/briefs/${active.id}/publish`, {});
      setBriefs((prev) => prev.map((b) => (b.id === data.id ? { ...b, ...data } : b)));
      select({ ...active, ...data, citations: data.citations ?? editCitations });
      setNotice('Đã ban hành ra Cổng Người dân.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không ban hành được — kiểm tra quyền admin_truyen_thong / admin_ops.');
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

  const remove = async (id: string) => {
    if (!window.confirm('Xóa bản tin này? Hành động không hoàn tác.')) return;
    setSaving(true); setError(null); setNotice(null);
    try {
      await apiDelete(`/admin/briefs/${id}`);
      setNotice('Đã xóa bản tin.');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi xóa bản tin');
    } finally { setSaving(false); }
  };

  const searchDocs = async () => {
    const q = searchQ.trim();
    if (!q) return;
    setSearching(true); setError(null); setKhoanHits([]); setPickedDoc(null);
    try {
      // Prefer exact so_hieu / vb_id lookup; fall back to filtering the recent list.
      try {
        const detail = await apiGet<VanBanHit & { tree?: KhoanHit[] }>(
          `/admin/legal/van-ban/${encodeURIComponent(q)}`,
        );
        setDocHits([{
          vb_id: detail.vb_id ?? detail.id ?? q,
          so_hieu: detail.so_hieu ?? q,
          ten: detail.ten,
        }]);
        const tree = Array.isArray(detail.tree) ? detail.tree : [];
        if (tree.length) {
          setKhoanHits(tree.slice(0, 40));
          setPickedDoc(detail.so_hieu ?? detail.vb_id ?? q);
        }
      } catch {
        const list = await apiGet<{ items: VanBanHit[] } | VanBanHit[]>('/admin/legal/van-ban');
        const items = Array.isArray(list) ? list : (list.items ?? []);
        const ql = q.toLowerCase();
        setDocHits(
          items
            .filter((d) =>
              [d.so_hieu, d.ten, d.vb_id, d.id].some((x) => String(x ?? '').toLowerCase().includes(ql)),
            )
            .slice(0, 12),
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tìm được văn bản');
      setDocHits([]);
    } finally {
      setSearching(false);
    }
  };

  const loadKhoans = async (doc: VanBanHit) => {
    const key = doc.so_hieu || doc.vb_id || doc.id;
    if (!key) return;
    setSearching(true); setError(null);
    try {
      const detail = await apiGet<{ tree?: KhoanHit[]; so_hieu?: string }>(
        `/admin/legal/van-ban/${encodeURIComponent(key)}`,
      );
      setPickedDoc(detail.so_hieu ?? key);
      setKhoanHits(Array.isArray(detail.tree) ? detail.tree.slice(0, 40) : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được khoản');
      setKhoanHits([]);
    } finally {
      setSearching(false);
    }
  };

  const addCitation = (k: KhoanHit) => {
    const kid = k.khoan_id || k.id;
    if (!kid) return;
    if (editCitations.some((c) => (c.khoan_id ?? c.id) === kid)) return;
    const quote = (k.noi_dung || k.tieu_de || '').slice(0, 280);
    setEditCitations((prev) => [
      ...prev,
      {
        khoan_id: kid,
        van_ban: pickedDoc || undefined,
        dieu: k.dieu || k.so_khoan || undefined,
        quote,
      },
    ]);
  };

  const addManualCitation = () => {
    const raw = searchQ.trim();
    if (!raw) return;
    if (editCitations.some((c) => (c.khoan_id ?? c.id) === raw)) return;
    setEditCitations((prev) => [...prev, { khoan_id: raw, quote: '', van_ban: raw }]);
    setNotice('Đã thêm căn cứ thủ công. Bấm Lưu để ghi lại.');
  };

  const removeCitation = (idx: number) => {
    setEditCitations((prev) => prev.filter((_, i) => i !== idx));
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
                <div
                  key={b.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => select(b)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') select(b); }}
                  className={`w-full text-left p-3 rounded-xl transition-all border cursor-pointer ${active?.id === b.id ? 'bg-primary/5 border-primary/20 shadow-sm' : 'bg-transparent border-transparent hover:bg-slate-50'}`}
                >
                  <div className="flex items-start justify-between mb-1 gap-2">
                    <span className="text-xs font-mono text-slate-400 truncate">{b.id.slice(0, 8)}</span>
                    <div className="flex items-center gap-1">
                      {statusBadge(b.status)}
                      <button
                        type="button"
                        title="Xóa bản tin"
                        onClick={(e) => { e.stopPropagation(); void remove(b.id); }}
                        className="p-1 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                      >
                        <Trash size={14} weight="bold" />
                      </button>
                    </div>
                  </div>
                  <h3 className={`text-sm font-bold line-clamp-2 leading-snug ${active?.id === b.id ? 'text-primary' : 'text-slate-700'}`}>{b.tieu_de}</h3>
                  {b.created_at && <p className="text-xs text-slate-500 mt-1 flex items-center gap-1"><Clock size={12} /> {new Date(b.created_at).toLocaleDateString('vi-VN')}</p>}
                </div>
              ))
            )}
          </div>
        </div>

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
                  <button
                    onClick={() => void remove(active.id)}
                    disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-red-50 border border-red-200 text-red-700 hover:bg-red-100 transition-colors disabled:opacity-50"
                  >
                    <Trash size={16} /> Xóa
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
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                    <LinkIcon size={16} /> Căn cứ pháp lý đính kèm
                    <span className="normal-case font-medium text-slate-400">(tuỳ chọn — vẫn ban hành được nếu trống)</span>
                  </label>

                  {editCitations.length === 0 ? (
                    <div className="mb-3 p-3 rounded-xl bg-slate-50 border border-dashed border-slate-300 text-sm text-slate-500">
                      Chưa có căn cứ. Bạn có thể tìm số hiệu bên dưới hoặc ban hành luôn.
                    </div>
                  ) : (
                    <div className="space-y-2 mb-3">
                      {editCitations.map((c, i) => (
                        <div key={citationId(c, i)} className="flex items-center gap-3 p-3 bg-blue-50/50 border border-blue-100 rounded-xl">
                          <FileText size={20} className="text-blue-500 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <h4 className="text-sm font-bold text-blue-900 truncate">{citationText(c)}</h4>
                            {(c.khoan_id ?? c.id) && <p className="text-xs text-blue-600 font-mono mt-0.5 truncate">ID: {c.khoan_id ?? c.id}</p>}
                          </div>
                          <button type="button" onClick={() => removeCitation(i)} className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50" title="Bỏ căn cứ">
                            <X size={16} weight="bold" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        value={searchQ}
                        onChange={(e) => setSearchQ(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') void searchDocs(); }}
                        className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                        placeholder="Tìm số hiệu, VD: 15/2020/ND-CP hoặc 15/2020/ND-CP::D1.K1"
                      />
                    </div>
                    <button type="button" onClick={() => void searchDocs()} disabled={searching || !searchQ.trim()} className="px-3 py-2.5 rounded-xl text-sm font-semibold bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                      {searching ? <Spinner size={16} className="animate-spin" /> : 'Tìm'}
                    </button>
                    <button type="button" onClick={addManualCitation} disabled={!searchQ.trim()} className="px-3 py-2.5 rounded-xl text-sm font-semibold bg-slate-100 border border-slate-200 text-slate-700 hover:bg-slate-200 disabled:opacity-50">
                      Thêm ID
                    </button>
                  </div>

                  {docHits.length > 0 && (
                    <div className="mt-2 space-y-1 max-h-36 overflow-y-auto">
                      {docHits.map((d) => {
                        const key = d.so_hieu || d.vb_id || d.id || '';
                        return (
                          <button
                            key={key}
                            type="button"
                            onClick={() => void loadKhoans(d)}
                            className={`w-full text-left px-3 py-2 rounded-lg text-sm border ${pickedDoc === (d.so_hieu || key) ? 'border-primary/40 bg-primary/5' : 'border-slate-100 hover:bg-slate-50'}`}
                          >
                            <span className="font-mono font-semibold text-slate-800">{d.so_hieu || key}</span>
                            {d.ten && <span className="text-slate-500 ml-2 line-clamp-1">{d.ten}</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {khoanHits.length > 0 && (
                    <div className="mt-2 space-y-1 max-h-48 overflow-y-auto border border-slate-100 rounded-xl p-2 bg-slate-50/80">
                      <p className="text-xs font-bold text-slate-500 px-1 mb-1">Chọn khoản để đính kèm</p>
                      {khoanHits.map((k, i) => {
                        const kid = k.khoan_id || k.id || `k-${i}`;
                        return (
                          <button
                            key={kid}
                            type="button"
                            onClick={() => addCitation(k)}
                            className="w-full text-left px-3 py-2 rounded-lg text-sm bg-white border border-slate-100 hover:border-primary/30 hover:bg-primary/5"
                          >
                            <span className="font-mono text-xs text-primary font-bold">{kid}</span>
                            <p className="text-slate-600 line-clamp-2 mt-0.5">{(k.noi_dung || k.tieu_de || '').slice(0, 160) || '—'}</p>
                          </button>
                        );
                      })}
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
