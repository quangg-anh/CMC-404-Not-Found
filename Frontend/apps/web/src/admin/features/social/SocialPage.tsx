import { useEffect, useState } from 'react';
import {
  ShareNetwork, Hash, ChatCircleText, Spinner, WarningCircle, ArrowClockwise,
  Link as LinkIcon, PaperPlaneRight, MagnifyingGlass, Globe, User, Clock, CheckCircle,
  YoutubeLogo, PlayCircle, Database, ChartLineUp,
} from '@phosphor-icons/react';
import { apiGet, apiPost } from '../../../lib/api';

// Backend returns loose Neo4j/Postgres property bags; keep the shapes permissive.
interface Topic {
  slug?: string;
  ten?: string;
  name?: string;
  chu_de?: string;
  post_count?: number;
  so_bai?: number;
}
interface Post {
  bai_dang_id?: string;
  id?: string;
  noi_dung?: string;
  content?: string;
  tac_gia?: string;
  comment_author_name?: string;
  nguon?: string;
  platform?: string;
  chu_de?: string;
  source_query?: string;
  ngay_dang?: string;
  thoi_gian?: string;
  url?: string;
  comment_url?: string;
  video_title?: string;
  video_url?: string;
  youtube_kind?: string;
  comment_text?: string;
  needs_review?: boolean;
}
interface ListResp<T> { items: T[]; total: number }
interface LinkPreview { url: string; domain: string; title: string; description: string; image?: string; candidate_text?: string }
interface CrawlResp {
  status: string;
  topics?: string[];
  platforms?: string[];
  dry_run?: boolean;
  collected: number;
  ingested: number;
  items?: Post[];
  errors?: { platform?: string; message: string }[];
  message?: string;
}

type Tab = 'topics' | 'posts' | 'ingest';

function topicName(t: Topic): string {
  return t.ten ?? t.name ?? t.chu_de ?? t.slug ?? 'Chủ đề';
}
function postText(p: Post): string {
  if (p.comment_text?.trim()) return p.comment_text.trim();
  const raw = p.noi_dung ?? p.content ?? '';
  if (!raw.trim()) return '(Không có nội dung)';

  const blocks = raw.split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean);
  if (p.youtube_kind === 'comment' && blocks.length > 1) {
    return blocks.slice(1).join('\n\n').trim();
  }

  const lines = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const cleanLines = lines.filter((line) => !/^(Người bình luận|Link video|Link bình luận|Tiêu đề video):/i.test(line));
  return (cleanLines.join('\n').trim() || raw.trim());
}
function postId(p: Post): string {
  return p.bai_dang_id ?? p.id ?? '';
}
function postAuthor(p: Post): string | undefined {
  return p.comment_author_name ?? p.tac_gia;
}

export default function SocialPage() {
  const [tab, setTab] = useState<Tab>('topics');
  const [metrics, setMetrics] = useState<{ posts: number; topics: number; loading: boolean }>({
    posts: 0,
    topics: 0,
    loading: true,
  });

  useEffect(() => {
    let alive = true;
    apiGet<{
      knowledge_graph: { social_posts_monitored: number; topic_count?: number };
    }>('/admin/dashboard/summary')
      .then((data) => {
        if (!alive) return;
        setMetrics({
          posts: data.knowledge_graph.social_posts_monitored ?? 0,
          topics: data.knowledge_graph.topic_count ?? 0,
          loading: false,
        });
      })
      .catch(() => {
        if (!alive) return;
        setMetrics((m) => ({ ...m, loading: false }));
      });
    return () => {
      alive = false;
    };
  }, []);

  const fmt = (n: number) => n.toLocaleString('vi-VN');

  return (
    <div className="mx-auto max-w-6xl pb-20">
      <div className="relative mb-8 overflow-hidden rounded-[1.75rem] border border-primary/15 bg-gradient-to-br from-[#0F172A] via-[#1E3A8A] to-primary p-7 text-white shadow-card md:p-8">
        <div className="pointer-events-none absolute -right-16 -top-16 h-52 w-52 rounded-full bg-accent/25 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 right-24 h-28 w-28 rounded-full bg-white/10 blur-2xl" />
        <div className="relative grid grid-cols-1 items-center gap-6 lg:grid-cols-[1fr_380px]">
          <div>
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-sky-100">
              <ShareNetwork size={16} weight="fill" aria-hidden /> Social Radar Live
            </div>
            <h1 className="font-display text-3xl font-extrabold tracking-tight md:text-4xl">Radar Mạng xã hội</h1>
            <p className="mt-3 max-w-2xl font-medium leading-relaxed text-sky-100/85">
              Crawl YouTube bằng token đã cấu hình, gom bình luận công khai theo chủ đề pháp lý, rồi đưa bài vào pipeline BE2 để giám sát.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <MetricCard icon={YoutubeLogo} label="Bài giám sát" value={metrics.loading ? '…' : fmt(metrics.posts)} />
            <MetricCard icon={Database} label="Chủ đề" value={metrics.loading ? '…' : fmt(metrics.topics)} />
            <MetricCard icon={ChartLineUp} label="Nguồn" value="YouTube" />
          </div>
        </div>
      </div>

      <CrawlPanel />

      <div className="mb-6 flex w-fit items-center gap-1 rounded-xl bg-primary-soft/60 p-1">
        {([['topics', 'Chủ đề', Hash], ['posts', 'Bài đăng', ChatCircleText], ['ingest', 'Thu thập & Preview', PaperPlaneRight]] as const).map(
          ([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-bold transition-all ${
                tab === id ? 'bg-white text-primary shadow-sm' : 'text-muted hover:text-ink'
              }`}
            >
              <Icon size={16} weight={tab === id ? 'fill' : 'regular'} /> {label}
            </button>
          ),
        )}
      </div>

      {tab === 'topics' && <TopicsTab />}
      {tab === 'posts' && <PostsTab />}
      {tab === 'ingest' && <IngestTab />}
    </div>
  );
}

function MetricCard({ icon: Icon, label, value }: { icon: React.FC<any>; label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white/10 border border-white/15 p-4 backdrop-blur">
      <Icon size={22} weight="fill" className="text-sky-200 mb-3" />
      <div className="text-[11px] uppercase tracking-widest text-sky-100/60 font-bold">{label}</div>
      <div className="text-sm font-black mt-1">{value}</div>
    </div>
  );
}

function CrawlPanel() {
  const [topicsText, setTopicsText] = useState('');
  const [limit, setLimit] = useState(5);
  const [dryRun, setDryRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CrawlResp | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runCrawl = async () => {
    if (running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    const topics = topicsText.split(',').map((x) => x.trim()).filter(Boolean);
    try {
      const data = await apiPost<CrawlResp>('/admin/social/crawl', {
        platforms: ['youtube'],
        topics: topics.length ? topics : null,
        limit_per_topic: limit,
        dry_run: dryRun,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi crawl MXH');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mb-8 rounded-[1.75rem] border border-slate-200 bg-white shadow-sm overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-0">
        <div className="p-6 md:p-7">
          <div className="flex items-center gap-3 mb-5">
            <div className="h-11 w-11 rounded-2xl bg-red-50 text-red-600 flex items-center justify-center">
              <YoutubeLogo size={24} weight="fill" />
            </div>
            <div>
              <h2 className="text-xl font-black text-slate-900">Crawl YouTube thật</h2>
              <p className="text-sm text-slate-500 font-medium">Dùng token trong `.env`, không nhập token trên UI.</p>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-[1fr_140px_160px] gap-3">
            <div>
              <label className="block text-xs font-black text-slate-500 uppercase tracking-wider mb-2">Chủ đề crawl</label>
              <input
                value={topicsText}
                onChange={(e) => setTopicsText(e.target.value)}
                placeholder="Bỏ trống để dùng BE2_SOCIAL_MONITOR_TOPICS, hoặc nhập: hoàn thuế, hóa đơn điện tử"
                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-semibold focus:outline-none focus:border-sky-300 focus:ring-4 focus:ring-sky-100"
              />
            </div>
            <div>
              <label className="block text-xs font-black text-slate-500 uppercase tracking-wider mb-2">Mỗi chủ đề</label>
              <input
                type="number"
                min={1}
                max={50}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value) || 1)}
                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-semibold focus:outline-none focus:border-sky-300 focus:ring-4 focus:ring-sky-100"
              />
            </div>
            <label className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 mt-6 text-sm font-bold text-slate-600 cursor-pointer">
              <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} className="accent-sky-600 h-4 w-4" />
              Chạy thử
            </label>
          </div>
          {error && <div className="mt-4"><ErrorBox msg={error} /></div>}
        </div>
        <div className="bg-slate-50 border-t lg:border-t-0 lg:border-l border-slate-200 p-6 flex flex-col justify-between gap-4">
          <button
            onClick={runCrawl}
            disabled={running}
            className="w-full bg-slate-950 text-white font-black px-5 py-4 rounded-2xl hover:bg-sky-700 transition-all flex items-center justify-center gap-2 disabled:opacity-60 shadow-lg shadow-slate-200"
          >
            {running ? <Spinner size={20} className="animate-spin" /> : <PlayCircle size={22} weight="fill" />}
            {running ? 'Đang crawl…' : 'Crawl ngay'}
          </button>
          {result ? (
            <div className="grid grid-cols-2 gap-3">
              <ResultStat label="Thu thập" value={result.collected} />
              <ResultStat label="Đã lưu" value={result.ingested} />
              <div className="col-span-2 text-xs font-semibold text-slate-500 leading-relaxed">
                {result.message || (result.errors?.length ? `Có ${result.errors.length} lỗi nguồn.` : 'Crawl hoàn tất. Bấm tab Bài đăng để xem dữ liệu.')}
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500 font-semibold leading-relaxed">
              Nếu bật “Chạy thử”, hệ thống chỉ gọi API và hiển thị mẫu, không ghi DB.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-4">
      <div className="text-2xl font-black text-slate-900">{value.toLocaleString('vi-VN')}</div>
      <div className="text-[11px] uppercase tracking-widest text-slate-400 font-black mt-1">{label}</div>
    </div>
  );
}

function TopicsTab() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    apiGet<ListResp<Topic>>('/admin/social/topics')
      .then((d) => { setTopics(d.items ?? []); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Lỗi tải chủ đề'))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  return (
    <Section title="Chủ đề đang giám sát" onReload={load}>
      {loading ? <Loading /> : error ? <ErrorBox msg={error} /> : topics.length === 0 ? (
        <Empty icon={Hash} msg="Chưa có chủ đề nào được giám sát." />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {topics.map((t, i) => (
            <div key={t.slug ?? i} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-sky-200 transition-all">
              <div className="w-10 h-10 rounded-xl bg-sky-50 text-sky-600 flex items-center justify-center mb-3">
                <Hash size={20} weight="bold" />
              </div>
              <h3 className="font-bold text-slate-800 leading-snug line-clamp-2">{topicName(t)}</h3>
              {t.slug && <p className="text-xs text-slate-400 font-mono mt-1">{t.slug}</p>}
              <div className="mt-3 pt-3 border-t border-slate-100 flex items-center gap-2 text-xs font-semibold text-slate-500">
                <ChatCircleText size={14} /> {(t.post_count ?? t.so_bai ?? 0).toLocaleString('vi-VN')} bài đăng
              </div>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function PostsTab() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewOnly, setReviewOnly] = useState(false);

  const load = () => {
    setLoading(true);
    apiGet<ListResp<Post>>(`/admin/social/posts${reviewOnly ? '?needs_review=true' : ''}`)
      .then((d) => { setPosts(d.items ?? []); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Lỗi tải bài đăng'))
      .finally(() => setLoading(false));
  };
  useEffect(load, [reviewOnly]);

  return (
    <Section
      title="Bài đăng đã thu thập"
      onReload={load}
      extra={
        <label className="flex items-center gap-2 text-sm font-semibold text-slate-600 cursor-pointer select-none">
          <input type="checkbox" checked={reviewOnly} onChange={(e) => setReviewOnly(e.target.checked)} className="accent-primary w-4 h-4" />
          Chỉ hiện bài cần review
        </label>
      }
    >
      {loading ? <Loading /> : error ? <ErrorBox msg={error} /> : posts.length === 0 ? (
        <Empty icon={ChatCircleText} msg="Chưa có bài đăng nào được thu thập." />
      ) : (
        <div className="space-y-3">
          {posts.map((p, i) => (
            <div key={postId(p) || i} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-sky-200 transition-all">
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                {(p.nguon || p.platform) && (
                  <span className="inline-flex items-center gap-1.5 text-xs font-bold text-red-700 bg-red-50 border border-red-100 px-2 py-1 rounded">
                    <Globe size={13} /> {p.nguon ?? p.platform}
                  </span>
                )}
                {postAuthor(p) && (
                  <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500">
                    <User size={13} /> {postAuthor(p)}
                  </span>
                )}
                {p.chu_de && <span className="text-xs font-mono text-sky-600 bg-sky-50 border border-sky-100 px-2 py-0.5 rounded">#{p.chu_de}</span>}
                {p.source_query && <span className="text-xs font-semibold text-violet-600 bg-violet-50 border border-violet-100 px-2 py-0.5 rounded">query: {p.source_query}</span>}
                {p.youtube_kind === 'comment' && <span className="text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded">Bình luận</span>}
                {p.needs_review && (
                  <span className="inline-flex items-center gap-1 text-xs font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                    <WarningCircle size={13} weight="fill" /> Cần review
                  </span>
                )}
                {(p.ngay_dang || p.thoi_gian) && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-slate-400 ml-auto">
                    <Clock size={13} /> {String(p.ngay_dang ?? p.thoi_gian)}
                  </span>
                )}
              </div>
              {p.video_title && <h3 className="font-black text-slate-900 mb-2 line-clamp-2">{p.video_title}</h3>}
              <p className="text-[15px] text-slate-800 leading-relaxed">{postText(p)}</p>
              {(p.comment_url || p.video_url || p.url) && (
                <div className="mt-4 pt-4 border-t border-slate-100 flex flex-wrap gap-2">
                  {p.comment_url && <a href={p.comment_url} target="_blank" rel="noreferrer" className="text-xs font-bold text-blue-600 bg-blue-50 px-3 py-1.5 rounded-lg hover:bg-blue-100">Mở bình luận</a>}
                  {(p.video_url || p.url) && <a href={p.video_url ?? p.url} target="_blank" rel="noreferrer" className="text-xs font-bold text-slate-600 bg-slate-100 px-3 py-1.5 rounded-lg hover:bg-slate-200">Mở video</a>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function IngestTab() {
  const [platform, setPlatform] = useState('facebook');
  const [url, setUrl] = useState('');
  const [noiDung, setNoiDung] = useState('');
  const [tacGia, setTacGia] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [previewUrl, setPreviewUrl] = useState('');
  const [preview, setPreview] = useState<LinkPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim() || !noiDung.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await apiPost<{ job_id: string; status: string; message: string }>('/admin/ingest/social', {
        platform, url: url.trim(), noi_dung: noiDung.trim(), tac_gia: tacGia.trim() || null,
      });
      setResult(`Job ${res.job_id.slice(0, 8)} — ${res.message}`);
      setUrl(''); setNoiDung(''); setTacGia('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi khi gửi bài đăng');
    } finally {
      setSubmitting(false);
    }
  };

  const runPreview = async () => {
    if (!previewUrl.trim() || previewing) return;
    setPreviewing(true);
    setPreview(null);
    try {
      const data = await apiPost<LinkPreview>('/admin/social/link-preview', { url: previewUrl.trim() });
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi khi lấy preview');
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Ingest form */}
      <form onSubmit={submit} className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
        <h3 className="font-bold text-slate-800 flex items-center gap-2"><PaperPlaneRight size={18} className="text-primary" /> Đẩy bài đăng vào pipeline</h3>
        <div>
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Nền tảng</label>
          <select value={platform} onChange={(e) => setPlatform(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10">
            <option value="facebook">Facebook</option>
            <option value="tiktok">TikTok</option>
            <option value="youtube">YouTube</option>
            <option value="news">Báo chí</option>
            <option value="forum">Diễn đàn</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">URL bài đăng *</label>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://facebook.com/..." className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10" />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Nội dung *</label>
          <textarea value={noiDung} onChange={(e) => setNoiDung(e.target.value)} rows={4} placeholder="Nội dung bài đăng cần phân tích…" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium resize-y focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10" />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Tác giả</label>
          <input value={tacGia} onChange={(e) => setTacGia(e.target.value)} placeholder="Tên tài khoản (tùy chọn)" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10" />
        </div>
        <button type="submit" disabled={submitting || !url.trim() || !noiDung.trim()} className="w-full bg-slate-900 text-white font-bold px-6 py-3 rounded-xl hover:bg-primary transition-colors flex items-center justify-center gap-2 disabled:opacity-50">
          {submitting ? <Spinner size={18} className="animate-spin" /> : <PaperPlaneRight size={18} weight="bold" />} Gửi vào pipeline
        </button>
        {result && <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl px-4 py-3 text-sm font-semibold flex items-center gap-2"><CheckCircle size={18} weight="fill" /> {result}</div>}
        {error && <ErrorBox msg={error} />}
      </form>

      {/* Link preview tool */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
        <h3 className="font-bold text-slate-800 flex items-center gap-2"><LinkIcon size={18} className="text-primary" /> Xem trước liên kết (Link Preview)</h3>
        <div className="flex gap-2">
          <input value={previewUrl} onChange={(e) => setPreviewUrl(e.target.value)} placeholder="Dán URL để trích xuất metadata…" className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10" />
          <button onClick={runPreview} disabled={previewing || !previewUrl.trim()} className="shrink-0 bg-slate-100 text-slate-700 font-bold px-4 rounded-xl hover:bg-slate-200 transition-colors flex items-center gap-2 disabled:opacity-50">
            {previewing ? <Spinner size={16} className="animate-spin" /> : <MagnifyingGlass size={16} weight="bold" />}
          </button>
        </div>
        {preview ? (
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            <div className="p-4">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-500 mb-2"><Globe size={14} /> {preview.domain}</div>
              <h4 className="font-bold text-slate-800 leading-snug mb-1">{preview.title}</h4>
              <p className="text-sm text-slate-500 leading-relaxed">{preview.description}</p>
              {preview.candidate_text && (
                <p className="text-xs text-slate-400 mt-3 pt-3 border-t border-slate-100 italic">{preview.candidate_text}</p>
              )}
              <a href={preview.url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 hover:underline mt-2 block truncate">{preview.url}</a>
            </div>
          </div>
        ) : (
          <div className="border border-dashed border-slate-300 rounded-xl p-8 text-center text-sm text-slate-400">
            Nhập URL và bấm tìm để xem trước nội dung.
          </div>
        )}
      </div>
    </div>
  );
}

/* ---- small shared UI helpers ---- */
function Section({ title, children, onReload, extra }: { title: string; children: React.ReactNode; onReload?: () => void; extra?: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-slate-900">{title}</h2>
        <div className="flex items-center gap-4">
          {extra}
          {onReload && (
            <button onClick={onReload} className="text-sm font-bold text-slate-500 hover:text-primary flex items-center gap-1.5 transition-colors">
              <ArrowClockwise size={16} /> Làm mới
            </button>
          )}
        </div>
      </div>
      {children}
    </div>
  );
}
function Loading() {
  return <div className="p-12 text-center text-slate-400 font-semibold flex items-center justify-center gap-2"><Spinner size={20} className="animate-spin" /> Đang tải…</div>;
}
function ErrorBox({ msg }: { msg: string }) {
  return <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-semibold">{msg}</div>;
}
function Empty({ icon: Icon, msg }: { icon: React.FC<any>; msg: string }) {
  return (
    <div className="p-16 text-center bg-white rounded-2xl border border-slate-200">
      <Icon size={40} className="text-slate-300 mx-auto mb-4" weight="fill" />
      <p className="text-slate-500 font-semibold">{msg}</p>
    </div>
  );
}
