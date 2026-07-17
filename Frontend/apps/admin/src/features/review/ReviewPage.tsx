import { useEffect, useState } from 'react';
import { 
  CheckCircle, XCircle, Clock, ListChecks, WarningCircle, ShieldCheck, Tag
} from '@phosphor-icons/react';
import { apiGet, apiPatch } from '../../lib/api';

interface ReviewItem {
  id: string;
  type: 'alert' | 'ingest' | 'brief';
  title: string;
  description: string;
  severity: 'high' | 'medium' | 'low';
  created_at: string;
  status: 'pending' | 'approved' | 'rejected';
}

const mockReviews: ReviewItem[] = [
  {
    id: "REV-001",
    type: "alert",
    title: "Phát hiện mâu thuẫn trong bài đăng MXH",
    description: "Một bài đăng trên Facebook khuyên người dân không cần nộp phạt nguội. Cần chuyên viên pháp chế xác nhận mức độ vi phạm để AI tạo bản tin phản bác.",
    severity: "high",
    created_at: new Date(Date.now() - 3600000).toISOString(),
    status: "pending"
  },
  {
    id: "REV-002",
    type: "ingest",
    title: "Cần duyệt Văn bản số hóa 168/2024/NĐ-CP",
    description: "Hệ thống bóc tách 32 Điều và 124 Khoản. Tồn tại 2 Khoản bị nhận diện lỗi do mờ nét chữ trên bản Scan PDF.",
    severity: "medium",
    created_at: new Date(Date.now() - 7200000).toISOString(),
    status: "pending"
  }
];

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    apiGet<ReviewItem[]>('/admin/review')
      .then((data) => {
        if (alive) {
          setItems(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (alive) {
          console.warn('Lỗi gọi API /admin/review:', err.message);
          setError('Hệ thống backend chưa phản hồi. Đang hiển thị dữ liệu giả lập (Mock).');
          setItems(mockReviews);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => { alive = false; };
  }, []);

  const handleAction = async (id: string, action: 'approved' | 'rejected') => {
    try {
      // Simulate API patch
      setItems(items.map(item => item.id === id ? { ...item, status: action } : item));
      await apiPatch(`/admin/review/${id}`, { status: action }).catch(() => {});
    } catch (err: any) {
      alert("Lỗi khi xử lý: " + err.message);
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'high': return <span className="bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5 rounded text-xs font-bold">Nghiêm trọng</span>;
      case 'medium': return <span className="bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded text-xs font-bold">Trung bình</span>;
      default: return <span className="bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded text-xs font-bold">Thấp</span>;
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'alert': return 'Cảnh báo rủi ro';
      case 'ingest': return 'Văn bản số hóa';
      case 'brief': return 'Bản tin AI';
      default: return 'Khác';
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-10">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
          <ListChecks size={28} weight="fill" className="text-primary" />
          Hàng đợi Duyệt (Review Queue)
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Nơi cán bộ quản lý phê duyệt các thay đổi, văn bản số hóa có lỗi hoặc các cảnh báo MXH cần xác thực.
        </p>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2">
          <WarningCircle size={20} weight="fill" className="text-amber-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="py-20 flex justify-center">
          <div className="flex items-center gap-2 text-primary font-bold">
            <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            Đang tải dữ liệu...
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {items.length === 0 ? (
            <div className="bg-surface rounded-2xl border border-border p-12 text-center text-slate-500 flex flex-col items-center">
              <ShieldCheck size={48} className="text-emerald-400 mb-3" weight="fill" />
              <p className="font-bold">Không có mục nào cần duyệt</p>
              <p className="text-sm mt-1">Hàng đợi của bạn đang trống.</p>
            </div>
          ) : (
            items.map((item) => (
              <div 
                key={item.id} 
                className={`bg-surface border rounded-2xl p-5 shadow-sm transition-all duration-300 ${
                  item.status === 'pending' ? 'border-border' : 
                  item.status === 'approved' ? 'border-emerald-200 bg-emerald-50/30 opacity-70' : 
                  'border-rose-200 bg-rose-50/30 opacity-70'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <div className="flex items-center gap-1.5 px-2 py-0.5 bg-slate-100 rounded text-xs font-bold text-slate-600">
                        <Tag size={12} /> {getTypeLabel(item.type)}
                      </div>
                      {getSeverityBadge(item.severity)}
                      <span className="text-xs text-slate-400 flex items-center gap-1 font-mono">
                        <Clock size={12} /> {new Date(item.created_at).toLocaleTimeString('vi-VN')}
                      </span>
                    </div>
                    <h3 className={`text-base font-bold mb-1 ${item.status !== 'pending' ? 'line-through text-slate-500' : 'text-slate-900'}`}>
                      {item.title}
                    </h3>
                    <p className={`text-sm ${item.status !== 'pending' ? 'text-slate-400' : 'text-slate-600'} leading-relaxed`}>
                      {item.description}
                    </p>
                  </div>
                  
                  {item.status === 'pending' ? (
                    <div className="flex flex-col gap-2 shrink-0 w-32">
                      <button 
                        onClick={() => handleAction(item.id, 'approved')}
                        className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 transition-colors"
                      >
                        <CheckCircle size={18} weight="bold" /> Duyệt
                      </button>
                      <button 
                        onClick={() => handleAction(item.id, 'rejected')}
                        className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold bg-white text-rose-600 border border-slate-200 hover:border-rose-200 hover:bg-rose-50 transition-colors"
                      >
                        <XCircle size={18} weight="bold" /> Từ chối
                      </button>
                    </div>
                  ) : (
                    <div className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold bg-slate-100 text-slate-500 border border-slate-200">
                      {item.status === 'approved' ? <CheckCircle size={18} className="text-emerald-500" /> : <XCircle size={18} className="text-rose-500" />}
                      Đã xử lý
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
