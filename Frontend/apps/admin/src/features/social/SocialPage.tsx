import { useEffect, useState } from 'react';
import {
  ShareNetwork, Hash, ChatCircleText, Spinner, WarningCircle, ArrowClockwise,
  Link as LinkIcon, PaperPlaneRight, MagnifyingGlass, Globe, User, Clock, CheckCircle,
} from '@phosphor-icons/react';
import { apiGet, apiPost } from '../../lib/api';

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
  nguon?: string;
  platform?: string;
  chu_de?: string;
  ngay_dang?: string;
  needs_review?: boolean;
}
interface ListResp<T> { items: T[]; total: number }
interface LinkPreview { url: string; domain: string; title: string; description: string; image?: string; candidate_text?: string }

type Tab = 'topics' | 'posts' | 'ingest';

function topicName(t: Topic): string {
  return t.ten ?? t.name ?? t.chu_de ?? t.slug ?? 'Chủ đề';
}
function postText(p: Post): string {
  return p.noi_dung ?? p.content ?? '(Không có nội dung)';
}
function postId(p: Post): string {
  return p.bai_dang_id ?? p.id ?? '';
}

export default function SocialPage() {
  const [tab, setTab] = useState<Tab>('topics');

  return (
    <div className="max-w-6xl mx-auto pb-20">
      <div className="mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-sky-50 border border-sky-200 text-sky-700 text-xs font-bold uppercase tracking-widest mb-3">
          <ShareNetwork size={16} weight="fill" /> Giám sát Mạng xã hội
        </div>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight">Radar Mạng xã hội</h1>
        <p className="text-slate-500 mt-2 font-medium">
          Theo dõi chủ đề pháp lý đang được bàn luận, bài đăng đã thu thập và đưa nội dung mới vào pipeline giám sát.
        </p>
      </div>

      <div className="flex items-center gap-1 mb-6 bg-slate-100 p-1 rounded-xl w-fit">
        {([['topics', 'Chủ đề', Hash], ['posts', 'Bài đăng', ChatCircleText], ['ingest', 'Thu thập & Preview', PaperPlaneRight]] as const).map(
          ([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-all ${
                tab === id ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-slate-800'
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
            <div key={postId(p) || i} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                {(p.nguon || p.platform) && (
                  <span className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-600 bg-slate-100 px-2 py-1 rounded">
                    <Globe size={13} /> {p.nguon ?? p.platform}
                  </span>
                )}
                {p.tac_gia && (
                  <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500">
                    <User size={13} /> {p.tac_gia}
                  </span>
                )}
                {p.chu_de && <span className="text-xs font-mono text-sky-600 bg-sky-50 px-2 py-0.5 rounded">#{p.chu_de}</span>}
                {p.needs_review && (
                  <span className="inline-flex items-center gap-1 text-xs font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                    <WarningCircle size={13} weight="fill" /> Cần review
                  </span>
                )}
                {p.ngay_dang && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-slate-400 ml-auto">
                    <Clock size={13} /> {p.ngay_dang}
                  </span>
                )}
              </div>
              <p className="text-[15px] text-slate-800 leading-relaxed">{postText(p)}</p>
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
