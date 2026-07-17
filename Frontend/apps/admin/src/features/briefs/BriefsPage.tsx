import { useEffect, useState } from 'react';
import { 
  Article, Plus, FloppyDisk, UploadSimple, CheckCircle, Clock, Archive, 
  FileText, WarningCircle, Link as LinkIcon, PenNib
} from '@phosphor-icons/react';
import { apiGet, apiPatch, apiPost } from '../../lib/api';

interface Citation {
  id: string;
  text: string;
}

interface Brief {
  id: string;
  title: string;
  content: string;
  status: 'draft' | 'review' | 'published' | 'archived';
  citations: Citation[];
  created_at: string;
}

const mockBriefs: Brief[] = [
  {
    id: "B-101",
    title: "Cảnh báo mạo danh Cảnh sát Giao thông phạt nguội",
    content: "Gần đây xuất hiện nhiều đối tượng gọi điện thoại tự xưng là CSGT, thông báo phạt nguội và yêu cầu người dân chuyển tiền vào tài khoản cá nhân. Người dân tuyệt đối không làm theo. Việc nộp phạt vi phạm giao thông chỉ thực hiện qua tài khoản Kho bạc Nhà nước hoặc Cổng Dịch vụ công Quốc gia.",
    status: "review",
    citations: [
      { id: "K1_D5_NĐ100", text: "Khoản 1 Điều 5, NĐ 100/2019/NĐ-CP" },
      { id: "D15_BLHS", text: "Điều 15 Luật An ninh mạng" }
    ],
    created_at: new Date().toISOString()
  },
  {
    id: "B-102",
    title: "Mức phạt vi phạm nồng độ cồn mới nhất",
    content: "Theo quy định, người điều khiển ô tô, xe máy tham gia giao thông mà trong máu hoặc hơi thở có nồng độ cồn sẽ bị phạt rất nặng. Mức phạt tối đa đối với ô tô lên tới 40 triệu đồng và tước GPLX 24 tháng.",
    status: "published",
    citations: [
      { id: "K10_D5_NĐ100", text: "Khoản 10 Điều 5, NĐ 100/2019/NĐ-CP" }
    ],
    created_at: new Date(Date.now() - 86400000).toISOString()
  }
];

export default function BriefsPage() {
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [activeBrief, setActiveBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form State
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');

  useEffect(() => {
    let alive = true;
    apiGet<Brief[]>('/admin/briefs')
      .then((data) => {
        if (alive) {
          setBriefs(data);
          if (data.length > 0) selectBrief(data[0]);
          setError(null);
        }
      })
      .catch((err) => {
        if (alive) {
          console.warn('Lỗi gọi API /admin/briefs:', err.message);
          setError('Backend chưa phản hồi. Đang hiển thị dữ liệu giả lập (Mock).');
          setBriefs(mockBriefs);
          selectBrief(mockBriefs[0]);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => { alive = false; };
  }, []);

  const selectBrief = (b: Brief) => {
    setActiveBrief(b);
    setEditTitle(b.title);
    setEditContent(b.content);
  };

  const getStatusBadge = (status: string) => {
    switch(status) {
      case 'published': return <span className="bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded text-xs font-bold border border-emerald-200">Đã ban hành</span>;
      case 'review': return <span className="bg-amber-50 text-amber-700 px-2 py-0.5 rounded text-xs font-bold border border-amber-200">Chờ duyệt</span>;
      case 'archived': return <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded text-xs font-bold border border-slate-200">Lưu trữ</span>;
      default: return <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded text-xs font-bold border border-blue-200">Bản nháp</span>;
    }
  };

  const handleSave = async (statusOverride?: 'draft' | 'review' | 'published') => {
    if (!activeBrief) return;
    setSaving(true);
    try {
      const payload = {
        title: editTitle,
        content: editContent,
        status: statusOverride || activeBrief.status
      };
      
      // Simulate API patch
      await new Promise(r => setTimeout(r, 600));
      
      const updated = { ...activeBrief, ...payload };
      setBriefs(prev => prev.map(b => b.id === updated.id ? updated : b));
      setActiveBrief(updated);
      
      // Nếu là publish thì gọi API riêng
      if (statusOverride === 'published') {
        apiPost(`/admin/briefs/${updated.id}/publish`, {}).catch(() => console.warn('Lỗi mock publish'));
      }
    } catch (err: any) {
      alert("Lỗi lưu dữ liệu: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-[calc(100vh-80px)] flex flex-col space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
          <Article size={28} weight="fill" className="text-primary" />
          Biên tập Tóm tắt & Bản tin (Briefs)
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Duyệt và biên tập các bản tóm tắt pháp lý do AI đề xuất trước khi ban hành ra Cổng Người dân.
        </p>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2 shrink-0">
          <WarningCircle size={20} weight="fill" className="text-amber-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Split View */}
      <div className="flex-1 flex gap-6 overflow-hidden pb-4">
        
        {/* Left: List */}
        <div className="w-[340px] flex flex-col bg-surface border border-border rounded-2xl overflow-hidden shadow-sm shrink-0">
          <div className="p-4 border-b border-border bg-slate-50 flex items-center justify-between">
            <h2 className="font-bold text-slate-700 text-sm">Danh sách Bản tin</h2>
            <button className="w-8 h-8 flex items-center justify-center rounded-lg bg-white border border-border text-slate-600 hover:text-primary hover:border-primary transition-colors">
              <Plus size={16} weight="bold" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
            {loading ? (
              <div className="p-4 text-center text-slate-400 text-sm">Đang tải...</div>
            ) : (
              briefs.map((b) => (
                <button
                  key={b.id}
                  onClick={() => selectBrief(b)}
                  className={`w-full text-left p-3 rounded-xl transition-all border ${
                    activeBrief?.id === b.id 
                      ? 'bg-primary/5 border-primary/20 shadow-sm' 
                      : 'bg-transparent border-transparent hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-start justify-between mb-1">
                    <span className="text-xs font-mono text-slate-400">{b.id}</span>
                    {getStatusBadge(b.status)}
                  </div>
                  <h3 className={`text-sm font-bold line-clamp-2 leading-snug ${activeBrief?.id === b.id ? 'text-primary' : 'text-slate-700'}`}>
                    {b.title}
                  </h3>
                  <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                    <Clock size={12} /> {new Date(b.created_at).toLocaleDateString('vi-VN')}
                  </p>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Right: Editor */}
        <div className="flex-1 flex flex-col bg-surface border border-border rounded-2xl overflow-hidden shadow-sm">
          {activeBrief ? (
            <>
              {/* Editor Toolbar */}
              <div className="p-4 border-b border-border bg-slate-50 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-slate-500 flex items-center gap-2">
                    <PenNib size={18} /> Chỉnh sửa
                  </span>
                  {getStatusBadge(activeBrief.status)}
                </div>
                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => handleSave('draft')}
                    disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 transition-colors"
                  >
                    <FloppyDisk size={16} /> Lưu nháp
                  </button>
                  <button 
                    onClick={() => handleSave('review')}
                    disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-amber-50 border border-amber-200 text-amber-700 hover:bg-amber-100 transition-colors"
                  >
                    <CheckCircle size={16} /> Gửi duyệt
                  </button>
                  {activeBrief.status !== 'published' && (
                    <button 
                      onClick={() => handleSave('published')}
                      disabled={saving}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-bold bg-primary text-white hover:bg-primary-dark transition-colors shadow-sm"
                    >
                      <UploadSimple size={16} weight="bold" /> Ban hành
                    </button>
                  )}
                </div>
              </div>

              {/* Editor Form */}
              <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Tiêu đề bản tin</label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50/50 text-slate-900 font-bold text-lg focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    placeholder="Nhập tiêu đề..."
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Nội dung (Content)</label>
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={8}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50/50 text-slate-800 text-base leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    placeholder="Viết nội dung bản tóm tắt..."
                  />
                </div>

                {/* Citations Box */}
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                    <LinkIcon size={16} /> Căn cứ pháp lý đính kèm
                  </label>
                  {activeBrief.citations.length === 0 ? (
                    <div className="p-4 border border-dashed border-slate-300 rounded-xl text-center text-sm text-slate-500">
                      Chưa có căn cứ pháp lý nào được liên kết.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {activeBrief.citations.map((cit) => (
                        <div key={cit.id} className="flex items-center gap-3 p-3 bg-blue-50/50 border border-blue-100 rounded-xl">
                          <FileText size={20} className="text-blue-500 shrink-0" />
                          <div className="flex-1">
                            <h4 className="text-sm font-bold text-blue-900">{cit.text}</h4>
                            <p className="text-xs text-blue-600 font-mono mt-0.5">ID: {cit.id}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
              Chọn một bản tin ở danh sách để bắt đầu biên tập
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
