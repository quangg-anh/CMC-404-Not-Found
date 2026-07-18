import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, WarningCircle, Tag, Clock, Info, ShieldCheck, TextT, BookmarkSimple } from '@phosphor-icons/react';
import { apiGet } from '../../../lib/api';

// Raw Khoan node from Neo4j (properties vary); we map defensively.
interface KhoanDetail {
  khoan_id?: string;
  id?: string;
  so_khoan?: string | number;
  dieu?: string | number;
  noi_dung?: string;
  content?: string;
  hieu_luc?: string;
  effective_date?: string;
  trang_thai?: string;
  status?: string;
  entities?: Record<string, unknown>[];
  [key: string]: unknown;
}

function pickContent(k: KhoanDetail): string {
  return (k.noi_dung as string) || (k.content as string) || (k.text as string) || '';
}
function pickName(k: KhoanDetail): string {
  if (k.so_khoan !== undefined && k.so_khoan !== null && k.so_khoan !== '') return `Khoản ${k.so_khoan}`;
  return (k.khoan_id as string) || (k.id as string) || 'Điều/Khoản';
}
function pickEffective(k: KhoanDetail): string | null {
  return (k.hieu_luc as string) || (k.effective_date as string) || (k.ngay_hieu_luc as string) || null;
}
function isActive(k: KhoanDetail): boolean {
  const s = String(k.trang_thai ?? k.status ?? '').toLowerCase();
  return s === '' || s.includes('hieu_luc') || s.includes('active') || s.includes('còn');
}
function entityText(e: Record<string, unknown>): string {
  return (e.noi_dung as string) || (e.mo_ta as string) || (e.text as string) || (e.ten as string) || (e.name as string) || JSON.stringify(e);
}

export default function KhoanPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [khoan, setKhoan] = useState<KhoanDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    apiGet<KhoanDetail>(`/admin/legal/khoan/${encodeURIComponent(id ?? '')}`)
      .then((data) => { if (alive) { setKhoan(data); setError(null); } })
      .catch((err) => { if (alive) setError(err instanceof Error ? err.message : 'Không tải được điều/khoản'); })
      .finally(() => { if (alive) setLoading(false); });
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

  if (error && !khoan) {
    return (
      <div className="max-w-3xl mx-auto py-16">
        <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-primary font-semibold mb-4 w-fit">
          <ArrowLeft size={16} weight="bold" /> Quay lại
        </button>
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2">
          <WarningCircle size={20} weight="fill" className="text-red-500 shrink-0" /> <span>{error}</span>
        </div>
      </div>
    );
  }
  if (!khoan) return null;

  const content = pickContent(khoan);
  const effective = pickEffective(khoan);
  const active = isActive(khoan);
  const entities = Array.isArray(khoan.entities) ? khoan.entities : [];

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-10">
      <div>
        <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-primary font-semibold mb-4 transition-colors w-fit">
          <ArrowLeft size={16} weight="bold" /> Quay lại
        </button>
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-3">
          <BookmarkSimple size={32} weight="fill" className="text-primary" />
          {pickName(khoan)}
        </h1>
        <p className="text-xs text-slate-400 font-mono mt-2">ID: {khoan.khoan_id || khoan.id || id}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-surface border border-border rounded-2xl p-6 md:p-8 shadow-sm">
            <div className="flex items-center gap-2 mb-6 border-b border-slate-100 pb-4">
              <TextT size={20} className="text-slate-400" />
              <h2 className="text-base font-bold text-slate-800 uppercase tracking-wide">Nguyên văn pháp lý</h2>
            </div>
            <div className="prose prose-slate max-w-none text-slate-800 leading-relaxed font-serif text-[1.05rem]">
              {content ? content.split('\n').map((line, idx) => (
                <p key={idx} className="mb-4 text-justify">{line}</p>
              )) : <p className="text-slate-400 italic">(Không có nội dung)</p>}
            </div>
          </div>

          <div className="bg-blue-50/50 border border-blue-100 rounded-2xl p-5 flex items-start gap-4">
            <Info size={24} weight="fill" className="text-blue-500 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-sm font-bold text-blue-900 mb-1">Xác thực Nguồn (Citation)</h4>
              <p className="text-xs text-blue-700 leading-relaxed">
                Nội dung được trích xuất trực tiếp từ hệ thống dữ liệu số hóa (Neo4j). Các thực thể liên quan được bóc tách tự động.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-surface border border-border rounded-2xl p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4">Thông tin Áp dụng</h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600 font-medium">Trạng thái</span>
                {active ? (
                  <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full text-xs font-bold flex items-center gap-1.5">
                    <ShieldCheck size={14} weight="fill" /> Còn hiệu lực
                  </span>
                ) : (
                  <span className="bg-slate-100 text-slate-600 border border-slate-200 px-2.5 py-1 rounded-full text-xs font-bold">Hết hiệu lực</span>
                )}
              </div>
              {effective && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 font-medium">Ngày hiệu lực</span>
                  <span className="text-sm text-slate-900 font-bold flex items-center gap-1.5">
                    <Clock size={16} className="text-slate-400" /> {effective}
                  </span>
                </div>
              )}
            </div>
          </div>

          {entities.length > 0 && (
            <div className="bg-surface border border-border rounded-2xl p-5 shadow-sm">
              <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Tag size={18} /> Thực thể liên quan ({entities.length})
              </h3>
              <ul className="space-y-2">
                {entities.map((e, idx) => (
                  <li key={idx} className="text-sm text-slate-700 bg-slate-50 border border-slate-100 px-3 py-2 rounded-lg leading-snug">
                    {entityText(e)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
