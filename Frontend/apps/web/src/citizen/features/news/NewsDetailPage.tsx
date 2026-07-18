import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, CalendarBlank, ShieldCheck, Tag, Spinner, CaretRight, WarningCircle } from '@phosphor-icons/react';
import { apiGet } from '../../../lib/api';
import { CitizenHeader } from '../../components/CitizenChrome';

interface BriefDetail {
  id: string;
  tieu_de: string;
  noidung?: string;
  noi_dung?: string;
  media_type: string;
  status: string;
  published_at?: string;
  citations?: {
    id?: string;
    text?: string;
    quote?: string;
    summary?: string;
    source?: string;
    source_url?: string;
    topic?: string;
    published_text?: string;
  }[];
}

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
          console.error('Lỗi gọi API /citizen/news/:id:', err.message);
          setError('Không thể tải bài viết từ máy chủ.');
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col bg-background font-sans">
        <CitizenHeader />
        <div className="flex flex-1 items-center justify-center gap-3 text-lg font-bold text-muted">
          <Spinner size={28} className="animate-spin text-civic" aria-hidden /> Đang tải bài viết…
        </div>
      </div>
    );
  }

  if (!news) return null;

  const citations = Array.isArray(news.citations) ? news.citations : [];
  const bodyText =
    news.noidung ||
    news.noi_dung ||
    citations.find((cit) => cit.summary)?.summary ||
    citations
      .map((cit) => [cit.quote].filter(Boolean).join('\n'))
      .join('\n\n') ||
    'Bản tin đang chờ biên tập nội dung chi tiết. Vui lòng xem căn cứ pháp lý và đường dẫn nguồn bên dưới.';

  return (
    <div className="min-h-screen bg-background pb-20 font-sans">
      <CitizenHeader />

      <div className="mx-auto max-w-3xl px-4 pt-6 sm:px-6">
        <Link to="/news" className="citizen-btn-secondary mb-6 inline-flex min-h-touch px-4 text-base">
          <ArrowLeft size={20} weight="bold" aria-hidden /> Về danh sách tin
        </Link>
      </div>

      <main id="main" className="mx-auto mt-2 max-w-3xl px-4 sm:px-6">
        {error && (
          <div className="mb-6 flex items-center gap-3 rounded-2xl border-2 border-amber-300 bg-amber-50 px-4 py-3 text-base font-semibold text-amber-900">
            <WarningCircle size={24} weight="fill" className="shrink-0 text-amber-500" aria-hidden />
            <span>{error}</span>
          </div>
        )}

        <article className="rounded-[28px] border-2 border-border bg-white p-7 shadow-soft sm:p-10">
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <span className="inline-flex min-h-touch items-center gap-2 rounded-2xl bg-civicSoft px-4 py-2 text-base font-bold text-civicDark">
              <Tag size={18} weight="fill" aria-hidden /> Tin pháp lý
            </span>
            {news.published_at && (
              <span className="inline-flex items-center gap-2 text-base font-semibold text-muted">
                <CalendarBlank size={20} aria-hidden /> {new Date(news.published_at).toLocaleDateString('vi-VN')}
              </span>
            )}
          </div>

          <h1 className="mb-8 font-display text-3xl font-extrabold leading-snug text-primary sm:text-4xl">
            {news.tieu_de}
          </h1>

          <div className="mb-12 max-w-none font-sans leading-relaxed text-primary">
            {bodyText
              .split('\n')
              .map((paragraph) => paragraph.trim())
              .filter(Boolean)
              .map((paragraph, idx) => (
                <p key={idx} className="mb-4 text-lg leading-relaxed sm:text-xl">
                  {paragraph}
                </p>
              ))}
          </div>

          <div className="mt-10 border-t-2 border-border pt-8">
            <h3 className="mb-4 flex items-center gap-2 font-display text-2xl font-bold text-primary">
              <ShieldCheck size={28} className="text-trust" weight="fill" aria-hidden /> Căn cứ pháp lý
            </h3>

            {citations.length > 0 ? (
              <div className="space-y-3">
                {citations.map((cit, idx) => (
                  <a
                    key={cit.id || cit.source_url || idx}
                    href={cit.source_url || '/van-ban'}
                    target={cit.source_url ? '_blank' : undefined}
                    rel={cit.source_url ? 'noreferrer' : undefined}
                    className="group flex min-h-touch items-center justify-between rounded-2xl border-2 border-transparent bg-background p-4 transition hover:border-trust hover:bg-trustSoft"
                  >
                    <div>
                      <p className="text-lg font-bold text-primary group-hover:text-trust">
                        {cit.text || cit.quote || cit.source || 'Nguồn tin pháp luật'}
                      </p>
                      {(cit.source_url || cit.id || cit.topic) && (
                        <p className="mt-1 text-base text-muted">
                          {[
                            cit.topic && `Chủ đề: ${cit.topic}`,
                            cit.published_text && `Công bố: ${cit.published_text}`,
                            cit.source_url && 'Mở bài gốc',
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </p>
                      )}
                    </div>
                    <CaretRight size={22} className="text-muted group-hover:text-trust" aria-hidden />
                  </a>
                ))}
              </div>
            ) : (
              <p className="text-lg text-muted">Không có căn cứ pháp lý nào được đính kèm.</p>
            )}
          </div>
        </article>
      </main>
    </div>
  );
}
