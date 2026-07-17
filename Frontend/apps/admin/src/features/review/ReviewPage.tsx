import { useEffect, useState } from 'react';
import { CheckCircle, XCircle, Clock, ListChecks, WarningCircle, ShieldCheck, Tag, Spinner } from '@phosphor-icons/react';
import { apiGet, apiPatch } from '../../lib/api';

// Matches GET /admin/review item shape.
interface ReviewItem {
  id: string;
  type: string; // social_post | legal_khoan | entity
  source?: string;
  content?: string;
  reason?: string;
  created_at?: string;
}
interface ReviewResponse { items: ReviewItem[]; total: number }

type LocalStatus = 'pending' | 'approved' | 'rejected';

const TYPE_LABELS: Record<string, string> = {
  social_post: 'Bài đăng MXH',
  legal_khoan: 'Điều/Khoản luật',
  entity: 'Thực thể bóc tách',
};
function typeLabel(t: string) { return TYPE_LABELS[t] || 'Mục cần duyệt'; }

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [statuses, setStatuses] = useState<Record<string, LocalStatus>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    apiGet<ReviewResponse>('/admin/review')
      .then((data) => { setItems(data.items ?? []); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : 'Lỗi tải hàng đợi duyệt'))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const handleAction = async (id: string, action: 'approve' | 'reject') => {
    setBusyId(id);
    setError(null);
    try {
      await apiPatch(`/admin/review/${id}`, { action });
      setStatuses((prev) => ({ ...prev, [id]: action === 'approve' ? 'approved' : 'rejected' }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi khi xử lý mục duyệt');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-10">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ListChecks size={28} weight="fill" className="text-primary" /> Hàng đợi Duyệt (Review Queue)
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Cán bộ phê duyệt các phần tử bị AI đánh dấu cần review (độ tin cậy thấp khi bóc tách BE1/BE2).
          </p>
        </div>
        <button onClick={load} className="text-sm font-bold text-slate-500 hover:text-primary flex items-center gap-1.5 transition-colors">
          <Spinner size={16} className={loading ? 'animate-spin' : 'hidden'} /> Làm mới
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2">
          <WarningCircle size={20} weight="fill" className="text-red-500 shrink-0" /> <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="py-20 flex justify-center">
          <div className="flex items-center gap-2 text-primary font-bold">
            <Spinner size={20} className="animate-spin" /> Đang tải dữ liệu...
          </div>
        </div>
      ) : items.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-border p-12 text-center text-slate-500 flex flex-col items-center">
          <ShieldCheck size={48} className="text-emerald-400 mb-3" weight="fill" />
          <p className="font-bold">Không có mục nào cần duyệt</p>
          <p className="text-sm mt-1">Hàng đợi của bạn đang trống.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {items.map((item) => {
            const st = statuses[item.id] ?? 'pending';
            return (
              <div
                key={item.id}
                className={`bg-surface border rounded-2xl p-5 shadow-sm transition-all duration-300 ${
                  st === 'pending' ? 'border-border' : st === 'approved' ? 'border-emerald-200 bg-emerald-50/30 opacity-70' : 'border-rose-200 bg-rose-50/30 opacity-70'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2 flex-wrap">
                      <div className="flex items-center gap-1.5 px-2 py-0.5 bg-slate-100 rounded text-xs font-bold text-slate-600">
                        <Tag size={12} /> {typeLabel(item.type)}
                      </div>
                      {item.reason && (
                        <span className="bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded text-xs font-bold">{item.reason}</span>
                      )}
                      {item.created_at && (
                        <span className="text-xs text-slate-400 flex items-center gap-1 font-mono">
                          <Clock size={12} /> {item.created_at}
                        </span>
                      )}
                    </div>
                    <p className={`text-sm leading-relaxed ${st !== 'pending' ? 'text-slate-400 line-through' : 'text-slate-700'}`}>
                      {item.content || '(Không có nội dung trích xuất)'}
                    </p>
                    <p className="text-xs text-slate-400 font-mono mt-2">ID: {item.id}</p>
                  </div>

                  {st === 'pending' ? (
                    <div className="flex flex-col gap-2 shrink-0 w-32">
                      <button
                        onClick={() => handleAction(item.id, 'approve')}
                        disabled={busyId === item.id}
                        className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 transition-colors disabled:opacity-50"
                      >
                        {busyId === item.id ? <Spinner size={16} className="animate-spin" /> : <CheckCircle size={18} weight="bold" />} Duyệt
                      </button>
                      <button
                        onClick={() => handleAction(item.id, 'reject')}
                        disabled={busyId === item.id}
                        className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold bg-white text-rose-600 border border-slate-200 hover:border-rose-200 hover:bg-rose-50 transition-colors disabled:opacity-50"
                      >
                        <XCircle size={18} weight="bold" /> Từ chối
                      </button>
                    </div>
                  ) : (
                    <div className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold bg-slate-100 text-slate-500 border border-slate-200">
                      {st === 'approved' ? <CheckCircle size={18} className="text-emerald-500" /> : <XCircle size={18} className="text-rose-500" />} Đã xử lý
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
