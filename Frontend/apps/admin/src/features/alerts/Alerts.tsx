import { useState } from 'react';
import { MagnifyingGlass, Funnel, ChartLineUp, Users, CheckCircle, Warning, CaretRight, Robot } from '@phosphor-icons/react';
import { RiskBadge, type RiskLabel } from '../../../../../packages/ui-legal/src/components/RiskBadge';
import { CitationCard } from '../../../../../packages/ui-legal/src/components/CitationCard';

interface AlertMeta {
  id: string;
  chuDe: string;
  claim: string;
  postUrl: string;
  volume: number;
  label: RiskLabel;
  confidence: 'high' | 'medium' | 'low';
  status: 'open' | 'triaged' | 'closed';
  createdAt: string;
  evidence: {
    van_ban: string;
    dieu: string;
    quote: string;
  };
}

export default function AlertsPage() {
  const [alerts] = useState<AlertMeta[]>([
    {
      id: 'ALT-8291',
      chuDe: 'Nồng độ cồn',
      claim: '"Công an bây giờ cứ thấy nồng độ cồn >0 là thu luôn xe máy vĩnh viễn, không cho chuộc lại"',
      postUrl: 'facebook.com/groups/giaothong/post123',
      volume: 12450,
      label: 'mau_thuan',
      confidence: 'high',
      status: 'open',
      createdAt: '2 giờ trước',
      evidence: {
        van_ban: 'Nghị định 100/2019/NĐ-CP',
        dieu: 'Điều 82, Khoản 1',
        quote: 'Để ngăn chặn ngay vi phạm hành chính, người có thẩm quyền được phép tạm giữ phương tiện tối đa đến 07 ngày trước khi ra quyết định xử phạt...'
      }
    },
    {
      id: 'ALT-8292',
      chuDe: 'Đất đai',
      claim: '"Đất không sổ đỏ cấp trước 2014 sẽ bị thu hồi không đền bù theo luật mới"',
      postUrl: 'tiktok.com/@tin_bds/video',
      volume: 8300,
      label: 'mau_thuan',
      confidence: 'high',
      status: 'open',
      createdAt: '4 giờ trước',
      evidence: {
        van_ban: 'Luật Đất đai 2024 (Sửa đổi)',
        dieu: 'Điều 138, Khoản 3',
        quote: 'Hộ gia đình, cá nhân sử dụng đất không có giấy tờ... trước ngày 01 tháng 7 năm 2014 mà không có tranh chấp thì được cấp Giấy chứng nhận quyền sử dụng đất...'
      }
    },
    {
      id: 'ALT-8293',
      chuDe: 'Lương cơ sở',
      claim: '"Từ 1/7 lương hưu sẽ tự động tăng thêm 30% đối với mọi đối tượng"',
      postUrl: 'zalo.me/g/news',
      volume: 3200,
      label: 'khong_ro',
      confidence: 'medium',
      status: 'triaged',
      createdAt: 'Hôm qua',
      evidence: {
        van_ban: 'Nghị định 73/2024/NĐ-CP',
        dieu: 'Điều 2',
        quote: 'Điều chỉnh tăng thêm 15% trên mức lương hưu, trợ cấp bảo hiểm xã hội và trợ cấp hằng tháng của tháng 6 năm 2024 đối với các đối tượng...'
      }
    }
  ]);

  return (
    <div className="max-w-6xl mx-auto pb-20 animate-fade-in-up">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-10">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-xs font-bold uppercase tracking-widest mb-3">
            <Warning size={16} weight="fill" /> Radar Mạng Xã Hội
          </div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Cảnh báo Tin giả & Sai lệch</h1>
          <p className="text-slate-500 mt-2 font-medium">
            AI tự động trích xuất các nhận định pháp lý trên MXH và đối chiếu với cơ sở dữ liệu luật Quốc gia.
          </p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              type="text" 
              placeholder="Tìm kiếm chủ đề..." 
              className="pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-medium w-64 focus:outline-none focus:border-brand transition-colors shadow-sm"
            />
          </div>
          <button className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-bold text-slate-700 hover:bg-slate-50 shadow-sm transition-colors">
            <Funnel size={18} /> Lọc
          </button>
        </div>
      </div>

      <div className="space-y-6">
        {alerts.map((alert) => (
          <div key={alert.id} className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden flex flex-col hover:border-brand/30 transition-colors group">
            
            {/* Header Area */}
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex flex-wrap gap-4 items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-xs font-black text-slate-400 bg-white px-2 py-1 rounded border border-slate-200 shadow-sm">
                  {alert.id}
                </span>
                <span className="text-sm font-bold text-slate-800">{alert.chuDe}</span>
                <span className="text-xs text-slate-500 font-medium">• {alert.createdAt}</span>
              </div>
              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                  <ChartLineUp size={16} /> Volume: <span className="text-slate-900 font-bold">{alert.volume.toLocaleString()}</span>
                </div>
                <div className="h-4 w-px bg-slate-300"></div>
                <div className="flex items-center gap-2 text-xs font-semibold">
                  Trạng thái: 
                  {alert.status === 'open' 
                    ? <span className="text-red-600 bg-red-50 px-2 py-0.5 rounded-md border border-red-100">Cần xử lý</span>
                    : <span className="text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-100">Đã kiểm duyệt</span>
                  }
                </div>
              </div>
            </div>

            {/* Content Area */}
            <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-8 relative">
              {/* Vertical divider line */}
              <div className="hidden lg:block absolute left-1/2 top-6 bottom-6 w-px bg-slate-100 -translate-x-1/2"></div>
              
              {/* Left Column: Social Claim */}
              <div className="flex flex-col">
                <div className="flex items-center gap-2 mb-3">
                  <Users size={18} className="text-blue-500" weight="fill" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Nội dung lan truyền MXH</span>
                </div>
                <div className="bg-slate-50 rounded-xl p-5 border border-slate-200/60 mb-4 relative">
                  <div className="absolute top-4 left-4 text-4xl text-slate-200 font-serif leading-none">"</div>
                  <p className="text-[15px] font-medium text-slate-800 leading-relaxed relative z-10 pl-6 italic">
                    {alert.claim}
                  </p>
                </div>
                <a href="#" className="text-xs font-bold text-blue-600 hover:underline flex items-center gap-1 w-fit">
                  Nguồn: {alert.postUrl}
                </a>
              </div>

              {/* Right Column: AI Evidence */}
              <div className="flex flex-col">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Robot size={18} className="text-brand" weight="fill" />
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-500">AI Đối chiếu Pháp luật</span>
                  </div>
                  <RiskBadge label={alert.label} confidence={alert.confidence} />
                </div>
                
                <CitationCard 
                  van_ban={alert.evidence.van_ban} 
                  dieu={alert.evidence.dieu} 
                  quote={alert.evidence.quote} 
                />
              </div>
            </div>

            {/* Actions Area */}
            <div className="px-6 py-4 bg-slate-50/50 border-t border-slate-100 flex items-center justify-end gap-3 opacity-0 translate-y-2 group-hover:opacity-100 group-hover:translate-y-0 transition-all duration-300">
              {alert.status === 'open' && (
                <>
                  <button className="px-4 py-2 rounded-lg text-sm font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 shadow-sm transition-colors flex items-center gap-2">
                    <CheckCircle size={16} /> Bỏ qua (Đánh dấu an toàn)
                  </button>
                  <button className="px-4 py-2 rounded-lg text-sm font-bold text-white bg-brand border border-brand hover:bg-red-700 shadow-md shadow-brand/20 transition-all flex items-center gap-2">
                    Sinh bài Đính chính <CaretRight size={16} weight="bold" />
                  </button>
                </>
              )}
            </div>

          </div>
        ))}
      </div>
    </div>
  );
}
