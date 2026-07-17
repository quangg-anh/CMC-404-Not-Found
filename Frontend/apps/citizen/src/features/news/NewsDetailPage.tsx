import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Article, CalendarBlank, ShieldCheck, Tag, Spinner, CaretRight, WarningCircle } from '@phosphor-icons/react';
import { apiGet } from '../../lib/api';

interface BriefDetail {
  id: string;
  tieu_de: string;
  noidung: string;
  media_type: string;
  status: string;
  published_at: string;
  citations: { id: string; text: string }[];
}

const mockBriefDetail: BriefDetail = {
  id: "B-101",
  tieu_de: "Cảnh báo mạo danh Cảnh sát Giao thông phạt nguội",
  noidung: "Gần đây xuất hiện nhiều đối tượng gọi điện thoại tự xưng là CSGT, thông báo phạt nguội và yêu cầu người dân chuyển tiền vào tài khoản cá nhân.\n\nNgười dân tuyệt đối không làm theo. Việc nộp phạt vi phạm giao thông chỉ thực hiện qua tài khoản Kho bạc Nhà nước hoặc Cổng Dịch vụ công Quốc gia.",
  media_type: "article",
  status: "published",
  published_at: new Date().toISOString(),
  citations: [
    { id: "K1_D5_NĐ100", text: "Khoản 1 Điều 5, NĐ 100/2019/NĐ-CP" },
    { id: "D15_BLHS", text: "Điều 15 Luật An ninh mạng" }
  ]
};

export default function NewsDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [news, setNews] = useState<BriefDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    apiGet<BriefDetail>(`/citizen/news/${id}`)
      .then((data) => {
        if (alive) {
          setNews(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (alive) {
          console.warn('Lỗi gọi API /citizen/news/:id:', err.message);
          setError('Không thể tải bài viết từ máy chủ. Hiển thị dữ liệu giả lập.');
          setNews({ ...mockBriefDetail, id: id || mockBriefDetail.id });
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => { alive = false; };
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f8fafc] font-sans flex items-center justify-center">
        <div className="flex items-center gap-2 text-slate-400 font-bold">
          <Spinner size={24} className="animate-spin text-brand" /> Đang tải bài viết...
        </div>
      </div>
    );
  }

  if (!news) return null;

  return (
    <div className="min-h-screen bg-[#f8fafc] font-sans pb-20">
      <header className="bg-white/80 backdrop-blur-xl border-b border-slate-200/80 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/news" className="flex items-center gap-2 text-slate-500 hover:text-slate-900 font-bold text-sm bg-slate-100 hover:bg-slate-200 px-4 py-2 rounded-full transition-all">
            <ArrowLeft size={16} weight="bold" /> Bản tin khác
          </Link>
          <div className="font-black text-slate-900 flex items-center gap-2 text-lg">
            <Article size={22} className="text-brand" weight="fill" /> Tin tức & Cảnh báo
          </div>
          <div className="w-[125px]"></div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 mt-10">
        {error && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium flex items-center gap-2 mb-6">
            <WarningCircle size={20} weight="fill" className="text-amber-500 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <article className="bg-white rounded-3xl p-8 sm:p-12 shadow-sm border border-slate-200">
          <div className="flex flex-wrap items-center gap-4 mb-6">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-brand/10 text-brand text-xs font-bold rounded-lg uppercase tracking-wider">
              <Tag size={14} weight="fill" /> Tin tức Pháp lý
            </span>
            {news.published_at && (
              <span className="inline-flex items-center gap-1.5 text-slate-500 text-sm font-medium">
                <CalendarBlank size={16} /> {new Date(news.published_at).toLocaleDateString('vi-VN')}
              </span>
            )}
          </div>

          <h1 className="text-3xl sm:text-4xl font-black text-slate-900 leading-tight mb-8">
            {news.tieu_de}
          </h1>

          <div className="prose prose-slate prose-lg max-w-none text-slate-800 leading-relaxed font-serif mb-12">
            {news.noidung.split('\n').map((paragraph, idx) => (
              <p key={idx} className="mb-4 text-justify">{paragraph}</p>
            ))}
          </div>

          {/* Căn cứ pháp lý Section */}
          <div className="mt-12 pt-8 border-t border-slate-100">
            <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
              <ShieldCheck size={24} className="text-emerald-500" weight="fill" /> Căn cứ pháp lý
            </h3>
            
            {news.citations.length > 0 ? (
              <div className="space-y-3">
                {news.citations.map(cit => (
                  <Link 
                    key={cit.id} 
                    to={`/van-ban`} // Citizen doesn't have a direct KhoanViewer yet, navigate to VanBan search
                    className="flex items-center justify-between p-4 bg-slate-50 rounded-xl hover:bg-emerald-50 hover:border-emerald-200 border border-transparent transition-colors group"
                  >
                    <div>
                      <p className="font-bold text-slate-800 group-hover:text-emerald-700">{cit.text}</p>
                      <p className="text-xs text-slate-500 font-mono mt-1 opacity-70">ID: {cit.id}</p>
                    </div>
                    <CaretRight size={20} className="text-slate-400 group-hover:text-emerald-500 transition-colors" />
                  </Link>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 italic">Không có căn cứ pháp lý nào được đính kèm.</p>
            )}
          </div>
        </article>
      </main>
    </div>
  );
}
