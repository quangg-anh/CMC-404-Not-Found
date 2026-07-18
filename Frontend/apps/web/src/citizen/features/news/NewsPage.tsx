import { useEffect, useState } from 'react';
import { Article, ShieldCheck, CaretRight, PlayCircle, Image as ImageIcon, FileText, Spinner } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { apiGet } from '../../../lib/api';
import { CitizenFooter, CitizenHeader } from '../../components/CitizenChrome';
import { Atmosphere } from '../../components/Atmosphere';

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
  if (mt === 'video') return <PlayCircle size={20} weight="fill" />;
  if (mt === 'image') return <ImageIcon size={20} weight="fill" />;
  return <FileText size={20} weight="fill" />;
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
    <div className="relative flex min-h-screen flex-col bg-background font-sans">
      <Atmosphere tone="section" />
      <CitizenHeader />

      <main id="main" className="relative mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6 sm:py-14">
        <div className="mb-12 max-w-3xl">
          <p className="inline-flex min-h-touch items-center gap-2 rounded-2xl bg-trustSoft px-4 py-2 text-base font-bold text-trust">
            <ShieldCheck size={20} weight="fill" aria-hidden /> Đã kiểm chứng pháp lý
          </p>
          <h1 className="ls-heading-accent mt-5 font-display text-3xl font-extrabold leading-tight sm:text-5xl">
            <span className="ls-brand-gradient">Tin pháp luật dễ đọc</span>
          </h1>
          <p className="mt-4 text-body-lg text-muted">
            Bài ngắn, chữ to, có căn cứ — phù hợp người lớn tuổi và học sinh.
          </p>
        </div>

        {error && (
          <div className="mx-auto mb-8 max-w-2xl rounded-2xl border-2 border-red-200 bg-red-50 px-6 py-4 text-center text-lg font-semibold text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center gap-3 py-24 text-lg font-semibold text-muted">
            <Spinner size={28} className="animate-spin" aria-hidden /> Đang tải tin tức…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-[28px] border-2 border-dashed border-border bg-white px-6 py-20 text-center">
            <Article size={52} className="mx-auto mb-4 text-slate-300" weight="fill" aria-hidden />
            <p className="text-xl font-bold text-muted">Chưa có bài tóm tắt nào được xuất bản.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <Link
                key={item.id}
                to={`/news/${item.id}`}
                className="group ls-card-wash flex min-h-[12rem] flex-col justify-between rounded-[28px] border-2 border-border bg-white p-6 shadow-soft transition duration-200 hover:-translate-y-1 hover:border-civic hover:shadow-card sm:p-7"
              >
                <div>
                  <div className="mb-5 flex items-start justify-between gap-3">
                    <span className="inline-flex min-h-touch items-center gap-2 rounded-2xl bg-background px-3 py-2 text-base font-bold text-primary">
                      {mediaIcon(item.media_type)} {mediaLabel(item.media_type)}
                    </span>
                    {item.published_at && (
                      <span className="text-base font-semibold text-muted">{item.published_at.slice(0, 10)}</span>
                    )}
                  </div>
                  <h3 className="font-display text-xl font-bold leading-snug text-primary line-clamp-3 group-hover:text-civicDark">
                    {item.tieu_de}
                  </h3>
                  {item.citations && item.citations.length > 0 && (
                    <span className="mt-4 inline-flex items-center gap-2 rounded-2xl bg-trustSoft px-3 py-2 text-base font-bold text-trust">
                      <ShieldCheck size={18} weight="fill" aria-hidden /> {item.citations.length} căn cứ
                    </span>
                  )}
                </div>
                <div className="mt-6 inline-flex items-center gap-1 text-lg font-bold text-civic">
                  Đọc bài <CaretRight size={20} weight="bold" aria-hidden />
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
      <CitizenFooter />
    </div>
  );
}
