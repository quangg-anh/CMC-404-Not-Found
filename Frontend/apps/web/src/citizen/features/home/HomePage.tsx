import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  MagnifyingGlass,
  BookOpen,
  Article,
  ArrowRight,
  ShieldCheck,
  ChatCircleText,
  CurrencyCircleDollar,
  Spinner,
  FileText,
  PlayCircle,
  Scales,
} from '@phosphor-icons/react';
import { apiGet } from '../../../lib/api';
import { CitizenFooter, CitizenHeader, SuggestionChips, SUGGESTIONS } from '../../components/CitizenChrome';
import { Reveal } from '../../components/Reveal';
import { AccentIllustration, Atmosphere } from '../../components/Atmosphere';

interface HomeBrief {
  id: string;
  tieu_de: string;
  media_type: string;
  published_at?: string;
}

function HeroSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  const goAsk = (q: string) => {
    const text = q.trim();
    if (!text) {
      navigate('/ask');
      return;
    }
    navigate(`/ask?q=${encodeURIComponent(text)}`);
  };

  return (
    <section className="ls-hero-banner relative w-full overflow-hidden border-b border-border min-h-[calc(100vh-76px)] flex flex-col justify-center">
      <div className="ls-hero-banner__plane absolute inset-0" aria-hidden />
      <Atmosphere tone="hero" showMark />

      <div className="ls-container relative grid items-center gap-8 py-12 lg:grid-cols-[1.15fr_0.85fr] lg:gap-12 lg:py-16">
        <div>
          <p className="ls-reveal inline-flex items-center gap-2 rounded-control border border-white/80 bg-white/85 px-3 py-1.5 text-sm font-semibold text-muted shadow-sm backdrop-blur-sm">
            <Scales size={16} className="text-primary" weight="fill" aria-hidden />
            Cổng hỏi đáp pháp luật cho công dân
          </p>

          <h1 className="ls-reveal ls-reveal-delay-1 mt-5 max-w-xl font-display text-3xl font-extrabold leading-tight tracking-tight text-ink sm:text-4xl lg:text-[2.85rem] lg:leading-[1.12]">
            Hiểu pháp luật dễ hơn với{' '}
            <span className="ls-brand-gradient">LexSocial AI</span>
          </h1>

          <p className="ls-reveal ls-reveal-delay-2 mt-4 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
            Đặt câu hỏi bằng ngôn ngữ đời thường, nhận câu trả lời kèm căn cứ pháp lý rõ ràng.
          </p>

          <form
            className="ls-reveal ls-reveal-delay-3 mt-7"
            aria-label="Ô hỏi trợ lý pháp lý"
            onSubmit={(e) => {
              e.preventDefault();
              goAsk(query);
            }}
          >
            <div className="ls-search-shell flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
              <div className="flex min-h-search flex-1 items-center gap-3 rounded-control bg-background/90 px-4">
                <MagnifyingGlass size={22} className="shrink-0 text-primary" weight="bold" aria-hidden />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ví dụ: Nghỉ thai sản được bao nhiêu ngày?"
                  className="w-full bg-transparent py-3 text-base font-medium text-ink placeholder:text-muted/80 focus:outline-none sm:text-[17px]"
                  autoComplete="off"
                  enterKeyHint="search"
                  aria-label="Nhập câu hỏi pháp lý"
                />
              </div>
              <button type="submit" className="ls-btn-primary w-full sm:w-auto sm:min-w-[8.5rem]">
                Hỏi ngay
                <ArrowRight size={18} weight="bold" aria-hidden />
              </button>
            </div>
          </form>

          <div className="ls-reveal ls-reveal-delay-4 mt-4">
            <p className="mb-2 text-sm font-semibold text-muted">Câu hỏi phổ biến</p>
            <SuggestionChips items={SUGGESTIONS} onSelect={goAsk} tinted />
          </div>
        </div>

        <aside
          className="ls-reveal ls-reveal-delay-3 ls-float ls-hero-banner__panel relative hidden overflow-hidden p-6 lg:block transition-transform duration-700 hover:-translate-y-2 hover:shadow-[0_40px_80px_-15px_rgba(37,87,214,0.15)] group"
          aria-hidden
        >
          <div className="ls-shimmer pointer-events-none absolute inset-0 opacity-30 group-hover:opacity-60 transition-opacity duration-700" />
          <div className="pointer-events-none absolute -right-2 -top-1 opacity-90 transition-transform duration-700 group-hover:scale-110 group-hover:-rotate-3">
            <AccentIllustration variant="chat" />
          </div>
          <div className="relative mb-3 flex items-center gap-2 text-sm font-semibold text-muted">
            <div className="relative flex h-8 w-8 items-center justify-center rounded-[10px] bg-primary-soft text-primary">
              <span className="absolute inset-0 animate-ping rounded-[10px] bg-primary opacity-20"></span>
              <ChatCircleText size={18} weight="fill" className="relative z-10" />
            </div>
            Ví dụ câu trả lời
          </div>
          <div className="relative rounded-control border border-white/70 bg-white p-4 shadow-sm transition-all duration-500 group-hover:shadow-md group-hover:border-white">
            <p className="text-sm font-bold text-ink flex items-center gap-2">
              Kết luận ngắn
              <span className="flex gap-0.5 items-center bg-primary/10 px-1.5 py-0.5 rounded-full">
                <span className="w-1 h-1 rounded-full bg-primary animate-[ping_1.5s_ease-in-out_infinite]" style={{ animationDelay: '0ms' }}></span>
                <span className="w-1 h-1 rounded-full bg-primary animate-[ping_1.5s_ease-in-out_infinite]" style={{ animationDelay: '300ms' }}></span>
                <span className="w-1 h-1 rounded-full bg-primary animate-[ping_1.5s_ease-in-out_infinite]" style={{ animationDelay: '600ms' }}></span>
              </span>
            </p>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Lao động nữ được nghỉ thai sản 6 tháng theo quy định hiện hành (khi đủ điều kiện).
            </p>
            <div className="relative mt-4 overflow-hidden rounded-control border border-success/20 bg-success-soft p-3 transition-colors duration-500 hover:bg-success/10 hover:border-success/30">
              <div className="absolute top-0 left-0 h-full w-[200%] -translate-x-full animate-[shimmer_3s_infinite] bg-gradient-to-r from-transparent via-success/10 to-transparent"></div>
              <p className="relative flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-success">
                <ShieldCheck size={14} weight="fill" /> Căn cứ pháp lý
              </p>
              <p className="relative mt-1.5 text-sm font-semibold text-ink transition-colors duration-300 hover:text-success">Bộ luật Lao động · Điều về thai sản</p>
              <p className="relative mt-1 text-xs text-muted">Ngày áp dụng: theo thời điểm bạn chọn khi hỏi</p>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}

function WhySection() {
  const cards = [
    {
      title: 'Có căn cứ pháp lý',
      desc: 'Mỗi câu trả lời kèm điều, khoản và số văn bản để bạn tự đối chiếu.',
      icon: ShieldCheck,
      tone: 'bg-success-soft text-success',
    },
    {
      title: 'Ngôn ngữ dễ hiểu',
      desc: 'Hỏi như đang nói chuyện — không cần thuộc thuật ngữ pháp lý.',
      icon: ChatCircleText,
      tone: 'bg-primary-soft text-primary',
    },
    {
      title: 'Miễn phí tra cứu',
      desc: 'Mở trang, đặt câu hỏi và xem căn cứ — không mất phí.',
      icon: CurrencyCircleDollar,
      tone: 'bg-accent-soft text-accent',
    },
  ] as const;

  return (
    <section className="ls-container py-10 sm:py-12" aria-labelledby="why-heading">
      <Reveal>
        <h2 id="why-heading" className="ls-heading-accent font-display text-2xl font-extrabold text-ink sm:text-3xl">
          Vì sao nên dùng LexSocial AI?
        </h2>
        <p className="mt-2 max-w-2xl text-base text-muted">
          Ba lý do ngắn gọn — dễ dùng kể cả khi ít tiếp xúc công nghệ.
        </p>
      </Reveal>
      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        {cards.map(({ title, desc, icon: IconCmp, tone }, i) => (
          <Reveal key={title} delay={(i + 1) as 1 | 2 | 3}>
            <div className="group ls-card-interactive ls-card-wash h-full p-5">
              <div
                className={`mb-4 flex h-11 w-11 items-center justify-center rounded-[12px] transition-transform duration-[220ms] ease-out group-hover:scale-110 ${tone}`}
              >
                <IconCmp size={22} weight="fill" aria-hidden />
              </div>
              <h3 className="text-lg font-bold text-ink">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted sm:text-base">{desc}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

function PathSection() {
  const paths = [
    { to: '/ask', title: 'Hỏi trợ lý AI', desc: 'Đặt câu hỏi và nhận căn cứ ngay.', icon: MagnifyingGlass },
    { to: '/news', title: 'Tin tức', desc: 'Tóm tắt chính sách, văn bản mới.', icon: Article },
    { to: '/van-ban', title: 'Văn bản', desc: 'Tra cứu theo số hiệu và điều khoản.', icon: BookOpen },
  ] as const;

  return (
    <section
      className="ls-path-band border-y border-border py-10 sm:py-12"
      aria-labelledby="paths-heading"
    >
      <Atmosphere tone="band" />
      <div className="ls-container relative">
        <Reveal>
          <h2 id="paths-heading" className="ls-heading-accent font-display text-2xl font-extrabold text-ink sm:text-3xl">
            Bạn muốn làm gì tiếp?
          </h2>
        </Reveal>
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {paths.map(({ to, title, desc, icon: IconCmp }, i) => (
            <Reveal key={to} delay={(i + 1) as 1 | 2 | 3}>
              <Link
                to={to}
                className="group flex h-full items-start gap-4 rounded-card border border-border bg-white/85 p-4 backdrop-blur-sm transition-all duration-[220ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-1 hover:border-primary/35 hover:bg-white hover:shadow-lift"
              >
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-primary-soft text-primary transition-all duration-[220ms] group-hover:scale-110 group-hover:bg-primary group-hover:text-white">
                  <IconCmp size={22} weight="fill" aria-hidden />
                </div>
                <div>
                  <p className="font-bold text-ink transition-colors duration-[220ms] group-hover:text-primary">
                    {title}
                  </p>
                  <p className="mt-1 text-sm text-muted">{desc}</p>
                </div>
              </Link>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function NewsHighlight() {
  const [news, setNews] = useState<HomeBrief[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<{ items: HomeBrief[] }>('/citizen/news')
      .then((data) => setNews((data.items ?? []).slice(0, 3)))
      .catch(() => setNews([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="ls-container py-10 sm:py-12" aria-labelledby="news-heading">
      <Reveal>
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="news-heading" className="ls-heading-accent font-display text-2xl font-extrabold text-ink sm:text-3xl">
              Tin pháp luật mới
            </h2>
            <p className="mt-2 text-base text-muted">Bài ngắn, có nguồn — dễ đọc nhanh.</p>
          </div>
          <Link to="/news" className="ls-btn-secondary !min-h-[44px] !text-sm">
            Xem tất cả <ArrowRight size={16} weight="bold" aria-hidden />
          </Link>
        </div>
      </Reveal>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-10 text-sm font-semibold text-muted">
          <Spinner size={20} className="animate-spin" aria-hidden /> Đang tải tin…
        </div>
      ) : news.length === 0 ? (
        <div className="rounded-card border border-dashed border-border bg-white px-6 py-10 text-center text-sm text-muted">
          Chưa có bài tóm tắt nào được xuất bản.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {news.map((item, i) => (
            <Reveal key={item.id} delay={((i % 3) + 1) as 1 | 2 | 3}>
              <Link to={`/news/${item.id}`} className="ls-card-interactive ls-card-wash flex h-full flex-col p-5">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-[12px] bg-primary-soft text-primary">
                  {item.media_type === 'video' ? (
                    <PlayCircle size={22} weight="fill" />
                  ) : (
                    <FileText size={22} weight="fill" />
                  )}
                </div>
                <h3 className="line-clamp-3 text-base font-bold leading-snug text-ink">{item.tieu_de}</h3>
                <p className="mt-auto pt-3 text-sm text-muted">
                  {item.published_at?.slice(0, 10) ?? 'Mới xuất bản'}
                </p>
              </Link>
            </Reveal>
          ))}
        </div>
      )}
    </section>
  );
}

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <CitizenHeader />
      <main id="main" className="flex-1">
        <HeroSearch />
        <WhySection />
        <PathSection />
        <NewsHighlight />
      </main>
      <CitizenFooter />
    </div>
  );
}
