import { useEffect, useState } from 'react';
import {
  PenNib, Plus, FloppyDisk, WarningCircle, Clock, CheckCircle, Export, Link as LinkIcon, ArrowClockwise,
} from '@phosphor-icons/react';
import { apiGet, apiPatch, apiPost } from '../../../lib/api';

type SuggestStatus = 'draft' | 'ready' | 'exported';

interface Suggestion {
  id: string;
  draft_text: string;
  alert_ids: string[];
  khoan_ids: string[];
  claim_labels: string[];
  status: SuggestStatus;
  created_by: string | null;
  created_at: string | null;
}
interface ListResp { items: Suggestion[]; total: number }

function statusBadge(s: SuggestStatus) {
  switch (s) {
    case 'exported': return <span className="bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded text-xs font-bold border border-emerald-200">Đã xuất</span>;
    case 'ready': return <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded text-xs font-bold border border-blue-200">Sẵn sàng</span>;
    default: return <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded text-xs font-bold border border-slate-200">Bản nháp</span>;
  }
}

export default function SuggestionsPage() {
  const [items, setItems] = useState<Suggestion[]>([]);
  const [active, setActive] = useState<Suggestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [editKhoan, setEditKhoan] = useState('');

  const select = (s: Suggestion) => {
    setActive(s);
    setEditText(s.draft_text ?? '');
    setEditKhoan((s.khoan_ids ?? [])[0] ?? '');
  };

  const load = (keepId?: string) => {
    setLoading(true);
    apiGet<ListResp>('/admin/suggestions')
      .then((d) => {
        const list = d.items ?? [];
        setItems(list);
        const pick = keepId ? list.find((x) => x.id === keepId) : list[0];
        if (pick) select(pick);
        else { setActive(null); }
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Lỗi tải đề xuất'))
      .finally(() => setLoading(false));
  };
  useEffect(() => load(), []);

  const generate = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await apiPost<Suggestion>('/admin/suggestions/generate', {
        tieu_de: 'Đề xuất đính chính mới',
        noi_dung_dinh_chinh: 'Nội dung đính chính (chỉnh sửa trước khi chuyển sẵn sàng).',
      });
      load(created.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi tạo đề xuất');
    } finally {
      setSaving(false);
    }
  };

  const save = async (statusOverride?: SuggestStatus) => {
    if (!active) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await apiPatch<Suggestion>(`/admin/suggestions/${active.id}`, {
        noi_dung_dinh_chinh: editText,
        khoan_doi_chieu_id: editKhoan.trim() || null,
        ...(statusOverride ? { status: statusOverride } : {}),
      });
      setItems((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      select(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu đề xuất');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-[calc(100vh-80px)] flex flex-col space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <PenNib size={28} weight="fill" className="text-primary" /> Đề xuất Đính chính (Suggestions)
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Soạn và chuyển trạng thái các đề xuất đính chính thông tin sai lệch. Đề xuất không xuất bản trực tiếp — chỉ chuyển sang bộ phận truyền thông.
          </p>
        </div>
        <button onClick={generate} disabled={saving} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold bg-primary text-white hover:bg-primary-dark shadow-sm transition-colors disabled:opacity-50">
          <Plus size={16} weight="bold" /> Tạo đề xuất
        </button>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2 shrink-0">
          <WarningCircle size={20} weight="fill" className="text-amber-500 shrink-0" /> <span>{error}</span>
        </div>
      )}

      <div className="flex-1 flex gap-6 overflow-hidden pb-4">
        {/* List */}
        <div className="w-[340px] flex flex-col bg-surface border border-border rounded-2xl overflow-hidden shadow-sm shrink-0">
          <div className="p-4 border-b border-border bg-slate-50 flex items-center justify-between">
            <h2 className="font-bold text-slate-700 text-sm">Danh sách đề xuất</h2>
            <button onClick={() => load(active?.id)} className="text-slate-400 hover:text-primary transition-colors"><ArrowClockwise size={16} /></button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loading ? (
              <div className="p-4 text-center text-slate-400 text-sm">Đang tải…</div>
            ) : items.length === 0 ? (
              <div className="p-6 text-center text-slate-400 text-sm">Chưa có đề xuất nào.<br />Bấm “Tạo đề xuất” để bắt đầu.</div>
            ) : (
              items.map((s) => (
                <button key={s.id} onClick={() => select(s)} className={`w-full text-left p-3 rounded-xl transition-all border ${active?.id === s.id ? 'bg-primary/5 border-primary/20 shadow-sm' : 'bg-transparent border-transparent hover:bg-slate-50'}`}>
                  <div className="flex items-start justify-between mb-1 gap-2">
                    <span className="text-xs font-mono text-slate-400 truncate">{s.id.slice(0, 8)}</span>
                    {statusBadge(s.status)}
                  </div>
                  <h3 className={`text-sm font-semibold line-clamp-2 leading-snug ${active?.id === s.id ? 'text-primary' : 'text-slate-700'}`}>
                    {(s.draft_text || '(trống)').split('\n')[0]}
                  </h3>
                  {s.created_at && (
                    <p className="text-xs text-slate-500 mt-1 flex items-center gap-1"><Clock size={12} /> {new Date(s.created_at).toLocaleDateString('vi-VN')}</p>
                  )}
                </button>
              ))
            )}
          </div>
        </div>

        {/* Editor */}
        <div className="flex-1 flex flex-col bg-surface border border-border rounded-2xl overflow-hidden shadow-sm">
          {active ? (
            <>
              <div className="p-4 border-b border-border bg-slate-50 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-slate-500 flex items-center gap-2"><PenNib size={18} /> Chỉnh sửa</span>
                  {statusBadge(active.status)}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => save()} disabled={saving} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50">
                    <FloppyDisk size={16} /> Lưu
                  </button>
                  {active.status === 'draft' && (
                    <button onClick={() => save('ready')} disabled={saving} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-blue-50 border border-blue-200 text-blue-700 hover:bg-blue-100 transition-colors disabled:opacity-50">
                      <CheckCircle size={16} /> Chuyển sẵn sàng
                    </button>
                  )}
                  {active.status === 'ready' && (
                    <button onClick={() => save('exported')} disabled={saving} className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-bold bg-primary text-white hover:bg-primary-dark transition-colors shadow-sm disabled:opacity-50">
                      <Export size={16} weight="bold" /> Xuất cho Truyền thông
                    </button>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Nội dung đính chính</label>
                  <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={10}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50/50 text-slate-800 text-base leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    placeholder="Soạn nội dung đính chính…" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-1.5"><LinkIcon size={16} /> Khoản pháp lý đối chiếu (ID)</label>
                  <input value={editKhoan} onChange={(e) => setEditKhoan(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50/50 text-slate-900 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    placeholder="VD: 15/2020/ND-CP::D1.K1" />
                </div>
                {active.claim_labels?.length > 0 && (
                  <div>
                    <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Nhãn đối chiếu</label>
                    <div className="flex flex-wrap gap-2">
                      {active.claim_labels.map((l, i) => <span key={i} className="text-xs font-bold bg-slate-100 text-slate-600 px-2 py-1 rounded">{l}</span>)}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">Chọn một đề xuất để biên tập, hoặc tạo mới.</div>
          )}
        </div>
      </div>
    </div>
  );
}
