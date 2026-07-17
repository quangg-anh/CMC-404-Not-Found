import { useEffect, useState } from 'react';
import { ArrowLeft, Article, ShieldCheck, CaretRight, PlayCircle, Image as ImageIcon, FileText, Spinner } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { apiGet } from '../../lib/api';

interface Brief {
  id: string;
  tieu_de: string;
  media_type: string;
  status: string;
  citations: unknown[];
  created_at?: string;
  published_at?: string;
}

interface NewsResponse {
  items: Brief[];
  total: number;
}

function mediaIcon(mt: string) {
  if (mt === 'video') return <PlayCircle size={16} weight="fill" />;
  if (mt === 'image') return <ImageIcon size={16} weight="fill" />;
  return <FileText size={16} weight="fill" />;
}

function mediaLabel(mt: string) {
  if (mt === 'video') return 'Video tóm tắt';
  if (mt === 'image') return 'Infographic';
  if (mt === 'audio') return 'Audio';
  return 'Bài viết';
}

export default function NewsPage() {
  const [items, setItems] = useState<Brief[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<NewsResponse>('/citizen/news')
      .then((data) => setItems(data.items ?? []))
      .catch((err) => setError(err instanceof Error ? err.message : 'Lỗi tải tin tức'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-[#f8fafc] font-sans">
      <header className="bg-white/80 backdrop-blur-xl border-b border-slate-200/80 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-slate-500 hover:text-slate-900 font-bold text-sm bg-slate-100 hover:bg-slate-200 px-4 py-2 rounded-full transition-all">
            <ArrowLeft size={16} weight="bold" /> Trang chủ
          </Link>
          <div className="flex flex-col items-center">
            <div className="font-black text-slate-900 flex items-center gap-2 text-lg">
              <Article size={22} className="text-brand" weight="fill" /> Tin tức & Cảnh báo
            </div>
          </div>
          <div className="w-[110px]"></div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-16">
        <div className="flex flex-col items-center text-center mb-16 animate-fade-in-up">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-bold uppercase tracking-widest mb-6">
            <ShieldCheck size={16} weight="fill" /> Đã kiểm chứng pháp lý
          </div>
          <h1 className="text-4xl sm:text-5xl font-black text-slate-900 tracking-tight leading-tight mb-4">
            Cập nhật Pháp luật <br /> <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand to-red-800">Nhanh & Chính xác nhất</span>
          </h1>
          <p className="text-slate-500 font-medium max-w-2xl text-lg">
            Các bài tóm tắt pháp lý đã được cán bộ kiểm duyệt và đối chiếu nguyên văn với Cơ sở dữ liệu trước khi xuất bản.
          </p>
        </div>

        {error && <div className="max-w-2xl mx-auto bg-red-50 border border-red-200 text-red-700 rounded-2xl px-6 py-4 text-sm font-semibold text-center">{error}</div>}

        {loading ? (
          <div className="py-24 text-center text-slate-400 font-semibold flex items-center justify-center gap-2">
            <Spinner size={22} className="animate-spin" /> Đang tải tin tức…
          </div>
        ) : items.length === 0 ? (
          <div className="py-24 text-center">
            <Article size={48} className="text-slate-300 mx-auto mb-4" weight="fill" />
            <p className="text-slate-500 font-semibold text-lg">Chưa có bài tóm tắt nào được xuất bản.</p>
            <p className="text-slate-400 mt-1">Nội dung sẽ xuất hiện sau khi cán bộ duyệt và xuất bản.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((item) => (
              <Link
                key={item.id}
                to={`/news/${item.id}`}
                className="group bg-white rounded-[28px] p-6 sm:p-8 shadow-sm hover:shadow-xl border border-slate-200 transition-all duration-300 hover:-translate-y-1 flex flex-col justify-between"
              >
                <div>
                  <div className="flex justify-between items-start mb-6">
                    <span className="bg-slate-100 text-slate-600 text-xs font-bold px-3 py-1 rounded-full flex items-center gap-1.5">
                      {mediaIcon(item.media_type)} {mediaLabel(item.media_type)}
                    </span>
                    {item.published_at && <span className="text-xs font-medium text-slate-400">{item.published_at.slice(0, 10)}</span>}
                  </div>
                  <h3 className="text-xl font-bold text-slate-900 leading-snug mb-3 group-hover:text-brand transition-colors line-clamp-3">
                    {item.tieu_de}
                  </h3>
                  {item.citations && item.citations.length > 0 && (
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-100">
                      <ShieldCheck size={14} weight="fill" /> {item.citations.length} căn cứ pháp lý
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 text-sm font-bold text-brand mt-6 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all">
                  Đọc chi tiết <CaretRight size={16} weight="bold" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
