import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { 
  ArrowLeft, BookOpenText, Gavel, WarningCircle, 
  Tag, Clock, Info, ShieldCheck, TextT, BookmarkSimple
} from '@phosphor-icons/react';
import { apiGet } from '../../lib/api';

interface Entity {
  id: string;
  type: 'HanhViCam' | 'CheTai' | 'DieuKien' | 'Khac';
  text: string;
}

interface KhoanDetail {
  id: string;
  name: string;
  van_ban_id: string;
  van_ban_name: string;
  chuong_name?: string;
  dieu_name: string;
  content: string;
  status: 'active' | 'expired' | 'draft';
  effective_date: string;
  entities: Entity[];
}

const mockKhoan: KhoanDetail = {
  id: "K1_D5_NĐ100",
  name: "Khoản 1",
  van_ban_id: "VB_100_2019",
  van_ban_name: "Nghị định 100/2019/NĐ-CP",
  chuong_name: "Chương II: Hành vi vi phạm, hình thức xử phạt...",
  dieu_name: "Điều 5. Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông",
  content: "Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:\na) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường;\nb) Chuyển hướng không nhường quyền đi trước cho: Người đi bộ, xe lăn của người khuyết tật qua đường tại nơi có vạch kẻ đường dành cho người đi bộ; xe thô sơ đang đi trên phần đường dành cho xe thô sơ.",
  status: "active",
  effective_date: "2020-01-01T00:00:00Z",
  entities: [
    { id: "HV1", type: "HanhViCam", text: "Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường" },
    { id: "HV2", type: "HanhViCam", text: "Chuyển hướng không nhường quyền đi trước" },
    { id: "CT1", type: "CheTai", text: "Phạt tiền từ 200.000 đồng đến 400.000 đồng" }
  ]
};

export default function KhoanPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [khoan, setKhoan] = useState<KhoanDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);

    apiGet<KhoanDetail>(`/admin/legal/khoan/${id}`)
      .then((data) => {
        if (alive) {
          setKhoan(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (alive) {
          console.warn('Lỗi gọi API /admin/legal/khoan:', err.message);
          setError('Hệ thống backend chưa sẵn sàng. Đang hiển thị dữ liệu giả lập.');
          // Dùng mock fallback
          setKhoan({ ...mockKhoan, id: id || mockKhoan.id });
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => { alive = false; };
  }, [id]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex items-center gap-3 text-muted text-sm font-semibold">
          <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          Đang tải dữ liệu điều/khoản...
        </div>
      </div>
    );
  }

  if (!khoan) return null;

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-10">
      {/* Nút quay lại & Breadcrumb */}
      <div>
        <button 
          onClick={() => navigate(-1)} 
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-primary font-semibold mb-4 transition-colors w-fit"
        >
          <ArrowLeft size={16} weight="bold" /> Quay lại
        </button>

        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-3 overflow-x-auto whitespace-nowrap hide-scrollbar">
          <BookOpenText size={16} />
          <Link to="/van-ban" className="hover:text-primary transition-colors truncate max-w-[200px]">{khoan.van_ban_name}</Link>
          <span className="text-slate-300">/</span>
          {khoan.chuong_name && (
            <>
              <span className="truncate max-w-[200px]">{khoan.chuong_name}</span>
              <span className="text-slate-300">/</span>
            </>
          )}
          <span className="truncate max-w-[300px]">{khoan.dieu_name}</span>
        </div>

        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-3">
          <BookmarkSimple size={32} weight="fill" className="text-primary" />
          {khoan.name}
        </h1>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2">
          <WarningCircle size={20} weight="fill" className="text-amber-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Cột trái: Nội dung nguyên văn (KhoanViewer) */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-surface border border-border rounded-2xl p-6 md:p-8 shadow-sm">
            <div className="flex items-center gap-2 mb-6 border-b border-slate-100 pb-4">
              <TextT size={20} className="text-slate-400" />
              <h2 className="text-base font-bold text-slate-800 uppercase tracking-wide">Nguyên văn pháp lý</h2>
            </div>
            
            <div className="prose prose-slate max-w-none text-slate-800 leading-relaxed font-serif text-[1.05rem]">
              {khoan.content.split('\n').map((line, idx) => (
                <p key={idx} className="mb-4 text-justify">{line}</p>
              ))}
            </div>
          </div>

          <div className="bg-blue-50/50 border border-blue-100 rounded-2xl p-5 flex items-start gap-4">
            <Info size={24} weight="fill" className="text-blue-500 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-sm font-bold text-blue-900 mb-1">Xác thực Nguồn (Citation)</h4>
              <p className="text-xs text-blue-700 leading-relaxed">
                Nội dung này được trích xuất trực tiếp từ hệ thống dữ liệu số hóa Cổng thông tin điện tử Chính phủ. 
                Các hành vi cấm và chế tài đã được bóc tách tự động bởi hệ thống AI LexSocial.
              </p>
            </div>
          </div>
        </div>

        {/* Cột phải: Metadata & Entities */}
        <div className="space-y-6">
          {/* Status Card */}
          <div className="bg-surface border border-border rounded-2xl p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4">Thông tin Áp dụng</h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600 font-medium">Trạng thái</span>
                {khoan.status === 'active' ? (
                  <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full text-xs font-bold flex items-center gap-1.5">
                    <ShieldCheck size={14} weight="fill" /> Còn hiệu lực
                  </span>
                ) : (
                  <span className="bg-slate-100 text-slate-600 border border-slate-200 px-2.5 py-1 rounded-full text-xs font-bold">
                    Hết hiệu lực
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600 font-medium">Ngày hiệu lực</span>
                <span className="text-sm text-slate-900 font-bold flex items-center gap-1.5">
                  <Clock size={16} className="text-slate-400" />
                  {new Date(khoan.effective_date).toLocaleDateString('vi-VN')}
                </span>
              </div>
            </div>
          </div>

          {/* Entities Bóc tách */}
          <div className="bg-surface border border-border rounded-2xl p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Tag size={18} /> Thực thể bóc tách (Entities)
            </h3>
            
            <div className="space-y-4">
              {/* Nhóm Hành vi cấm */}
              {khoan.entities.filter(e => e.type === 'HanhViCam').length > 0 && (
                <div>
                  <div className="text-xs font-bold text-rose-600 mb-2 flex items-center gap-1.5">
                    <WarningCircle size={14} weight="fill" /> Hành vi vi phạm / Bị cấm
                  </div>
                  <ul className="space-y-2">
                    {khoan.entities.filter(e => e.type === 'HanhViCam').map(e => (
                      <li key={e.id} className="text-sm text-slate-700 bg-rose-50 border border-rose-100 px-3 py-2 rounded-lg leading-snug">
                        {e.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Nhóm Chế tài */}
              {khoan.entities.filter(e => e.type === 'CheTai').length > 0 && (
                <div>
                  <div className="text-xs font-bold text-amber-600 mb-2 mt-4 flex items-center gap-1.5">
                    <Gavel size={14} weight="fill" /> Chế tài / Mức phạt
                  </div>
                  <ul className="space-y-2">
                    {khoan.entities.filter(e => e.type === 'CheTai').map(e => (
                      <li key={e.id} className="text-sm text-slate-700 bg-amber-50 border border-amber-100 px-3 py-2 rounded-lg leading-snug">
                        {e.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            
          </div>
        </div>

      </div>
    </div>
  );
}
