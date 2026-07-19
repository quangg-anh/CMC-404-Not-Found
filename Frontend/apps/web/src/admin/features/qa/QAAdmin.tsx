import { useState, useRef, useEffect } from 'react';
import { PaperPlaneRight, User, Robot, ShieldCheck, WarningCircle, CaretRight, Path, Sparkle, Database, Quotes, Trash } from '@phosphor-icons/react';
import { CitationCard } from '../../../../../../packages/ui-legal/src/components/CitationCard';
import { AnswerMarkdown } from '../../../../../../packages/ui-legal/src/components/AnswerMarkdown';
import { apiPost } from '../../../lib/api';

interface BackendCitation {
  khoan_id?: string;
  quote: string;
  van_ban: string;
  dieu: string;
  score?: number;
}

interface GraphNode {
  id: string;
  type: string;
  label?: string;
  title?: string;
  text?: string;
}
interface GraphEdge {
  source: string;
  target: string;
  type: string;
}
// The backend returns graph_paths as objects ({khoan_id, nodes, edges}), NOT plain strings.
interface GraphPath {
  khoan_id?: string;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
}

interface QAResponse {
  answer: string;
  citations: BackendCitation[];
  graph_paths: GraphPath[];
  confidence: 'high' | 'medium' | 'low';
  unverified?: boolean;
  degraded?: boolean;
  refuse_reason?: string[];
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: BackendCitation[];
  confidence?: 'high' | 'medium' | 'low';
  unverified?: boolean;
  degraded?: boolean;
  refuseReason?: string[];
  isTyping?: boolean;
  graphPaths?: GraphPath[];
}

// Turn one graph node into a short human label (never render the raw object → avoids the
// "Objects are not valid as a React child" crash that blanked the screen).
function dieuNumber(label?: string, id?: string): string {
  const raw = (label || '').trim();
  if (raw && !raw.includes('::') && !/^D\d+/i.test(raw)) return raw;
  const fromLabel = raw.match(/D(\d+)/i);
  if (fromLabel) return fromLabel[1];
  const fromId = (id || '').match(/::D(\d+)/i);
  return fromId?.[1] || raw || '';
}

function nodeLabel(n: GraphNode): string {
  const t = (n.type || '').toLowerCase();
  if (t === 'dieu') {
    const num = dieuNumber(n.label, n.id);
    return num ? `Điều ${num}` : 'Điều';
  }
  if (t === 'khoan') {
    if (n.title && !n.title.includes('::')) return n.title;
    const m = (n.label || n.id || '').match(/\.?K(\d+)/i);
    return m ? `Khoản ${m[1]}` : 'Khoản';
  }
  return n.title || n.label || n.id || '—';
}

function GraphPathBreadcrumb({ paths }: { paths: GraphPath[] }) {
  const valid = (paths ?? []).filter((p) => Array.isArray(p?.nodes) && p.nodes.length > 0);
  if (valid.length === 0) return null;
  return (
    <div className="mt-4 rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4 shadow-sm space-y-3">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-indigo-700">
        <Path size={15} weight="bold" />
        <span>Đường dẫn tri thức</span>
      </div>
      {valid.map((p, pi) => (
        <div key={p.khoan_id ?? pi} className="flex flex-wrap items-center gap-1.5">
          {(p.nodes ?? []).map((n, i) => (
            <span key={n.id ?? i} className="flex items-center gap-2">
              {i > 0 && <CaretRight size={12} className="text-indigo-300" />}
              <span className="rounded-full border border-indigo-100 bg-white px-3 py-1 text-[11px] font-semibold text-indigo-700 shadow-sm">{nodeLabel(n)}</span>
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

const generateId = () => crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15);

function confidenceStyle(confidence?: 'high' | 'medium' | 'low') {
  if (confidence === 'high') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (confidence === 'medium') return 'border-amber-200 bg-amber-50 text-amber-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

function confidenceLabel(confidence?: 'high' | 'medium' | 'low') {
  if (confidence === 'high') return 'Độ tin cậy cao';
  if (confidence === 'medium') return 'Độ tin cậy vừa';
  return 'Tham khảo';
}

export default function QAAdminPage() {
  const welcomeMessage: ChatMessage = { id: 'welcome', role: 'assistant', content: 'Chào bạn, tôi là trợ lý LexSocial. Hãy nhập tình huống pháp lý, số hiệu văn bản hoặc câu hỏi cần tra cứu. Khi hệ thống có dữ liệu xác thực, câu trả lời sẽ kèm trích dẫn và đường dẫn tri thức.' };
  const [messages, setMessages] = useState<ChatMessage[]>([
    welcomeMessage,
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = input.trim();
    if (!question || isLoading) return;

    const userMsgId = generateId();
    setMessages((prev) => [...prev, { id: userMsgId, role: 'user', content: question }]);
    setInput('');
    setIsLoading(true);

    const typingId = generateId();
    setMessages((prev) => [...prev, { id: typingId, role: 'assistant', content: '', isTyping: true }]);

    try {
      const data = await apiPost<QAResponse>('/admin/qa/ask', { question, graph_paths_enabled: true, audience: 'admin' });
      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? { id: typingId, role: 'assistant', content: data.answer, citations: data.citations ?? [], confidence: data.confidence, graphPaths: data.graph_paths, unverified: Boolean(data.unverified), degraded: Boolean(data.degraded), refuseReason: data.refuse_reason }
            : m,
        ),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Lỗi không xác định';
      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? { id: typingId, role: 'assistant', content: `Không thể kết nối máy chủ QA (${message}).`, confidence: 'low' }
            : m,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-7rem)] max-w-6xl flex-col overflow-hidden rounded-[28px] border border-white/70 bg-white/80 shadow-[0_24px_80px_rgba(52,71,103,0.12)] backdrop-blur">
      <header className="relative overflow-hidden border-b border-slate-100 bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 p-6 text-white">
        <div className="absolute -right-20 -top-20 h-56 w-56 rounded-full bg-cyan-400/20 blur-3xl" />
        <div className="absolute bottom-0 left-1/3 h-24 w-72 rounded-full bg-blue-500/20 blur-2xl" />
        <div className="relative flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/12 ring-1 ring-white/20 shadow-2xl">
              <Robot size={30} weight="fill" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-2xl font-black tracking-tight">QA pháp lý nội bộ</h2>
                <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-100">AI + RAG</span>
              </div>
              <p className="mt-1 max-w-2xl text-sm text-slate-300">Trả lời dễ đọc, ưu tiên căn cứ đã xác thực; nếu chưa có dữ liệu, AI chỉ trả lời dạng tham khảo.</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs md:w-80">
            <div className="rounded-2xl border border-white/10 bg-white/10 p-3">
              <div className="flex items-center gap-2 font-bold text-emerald-200"><ShieldCheck size={16} weight="fill" /> Evidence-first</div>
              <p className="mt-1 text-slate-300">Trích dẫn rõ nguồn</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/10 p-3">
              <div className="flex items-center gap-2 font-bold text-cyan-200"><Database size={16} weight="fill" /> Knowledge graph</div>
              <p className="mt-1 text-slate-300">Hiện đường dẫn tri thức</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setMessages([welcomeMessage])}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-xs font-black text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={isLoading || messages.length <= 1}
            title="Xóa lịch sử hỏi đáp đang hiển thị để giảm lag khi test lâu"
          >
            <Trash size={15} weight="bold" /> Xóa hội thoại
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top_left,#eff6ff,transparent_35%),linear-gradient(180deg,#f8fafc,#eef2f7)] p-5 sm:p-8">
        <div className="mx-auto max-w-5xl space-y-7">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-4 ${msg.role === 'user' ? 'ml-auto max-w-3xl flex-row-reverse' : 'max-w-5xl'}`}>
            <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl shadow-sm ring-1 ${msg.role === 'user' ? 'bg-slate-900 text-white ring-slate-800' : 'bg-white text-blue-600 ring-blue-100'}`}>
              {msg.role === 'user' ? <User size={20} weight="fill" /> : <Robot size={20} weight="fill" className="text-secondaryAccent" />}
            </div>
            <div className={`flex max-w-full flex-1 flex-col gap-3 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              {msg.role === 'assistant' && msg.id !== 'welcome' && !msg.isTyping && (
                <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-[0.14em] ${confidenceStyle(msg.confidence)}`}>
                  <Sparkle size={13} weight="fill" /> {confidenceLabel(msg.confidence)}
                </div>
              )}
              <div className={`max-w-full rounded-[22px] p-5 text-[15px] leading-7 shadow-sm ring-1 ${msg.role === 'user' ? 'whitespace-pre-wrap rounded-tr-md bg-slate-900 text-white ring-slate-900' : 'rounded-tl-md bg-white text-slate-800 ring-slate-200/80'}`}>
                {msg.isTyping ? (
                  <div className="flex items-center gap-1.5 h-5">
                    <span className="w-2 h-2 rounded-full bg-secondaryAccent/50 animate-bounce"></span>
                    <span className="w-2 h-2 rounded-full bg-secondaryAccent/70 animate-bounce [animation-delay:-0.15s]"></span>
                    <span className="w-2 h-2 rounded-full bg-secondaryAccent/90 animate-bounce [animation-delay:-0.3s]"></span>
                  </div>
                ) : msg.role === 'assistant' ? (
                  <AnswerMarkdown content={msg.content} density="compact" />
                ) : (
                  msg.content
                )}
              </div>
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-1 w-full space-y-4 rounded-[26px] border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-cyan-50 p-4 shadow-[0_18px_50px_rgba(16,185,129,0.10)] md:min-w-[620px]">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-xs font-black text-emerald-700 uppercase tracking-[0.18em]">
                      <ShieldCheck size={17} weight="fill" /> Trích xuất pháp lý đã xác thực
                    </div>
                    <span className="rounded-full border border-emerald-200 bg-white px-3 py-1 text-[11px] font-bold text-emerald-700">
                      {msg.citations.length} căn cứ
                    </span>
                  </div>
                  <div className="flex items-start gap-2 rounded-2xl border border-emerald-100 bg-white/80 px-4 py-3 text-xs font-semibold leading-6 text-emerald-800">
                    <Quotes size={16} weight="fill" className="mt-1 shrink-0" />
                    Nội dung dưới đây là đoạn trích nguồn hệ thống dùng để tạo câu trả lời. Kiểm tra điều/khoản trước khi phát hành hoặc tư vấn chính thức.
                  </div>
                  <div className="grid gap-3">
                    {msg.citations.map((cit, idx) => (
                      <CitationCard key={idx} van_ban={cit.van_ban} dieu={cit.dieu} quote={cit.quote} khoan_id={cit.khoan_id} />
                    ))}
                  </div>
                </div>
              )}
              {msg.graphPaths && msg.graphPaths.length > 0 && (
                <GraphPathBreadcrumb paths={msg.graphPaths} />
              )}
              {msg.role === 'assistant' && !msg.isTyping && msg.unverified && !(msg.citations?.length) && msg.id !== 'welcome' && (
                <div className="w-full rounded-3xl border border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50 p-4 text-amber-900 shadow-sm md:min-w-[620px]">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 ring-1 ring-amber-200">
                      <WarningCircle size={18} weight="fill" />
                    </div>
                    <div>
                      <div className="text-sm font-black">Chưa có căn cứ pháp lý xác thực</div>
                      <p className="mt-1 text-xs font-semibold leading-6 text-amber-800">
                        Hệ thống chưa tìm thấy điều/khoản/số văn bản phù hợp trong dữ liệu đã nạp. Câu trả lời chỉ là tham khảo, không nên dùng để kết luận mức tiền, điều kiện hưởng, xử phạt hoặc nghĩa vụ pháp lý.
                      </p>
                      {msg.refuseReason && msg.refuseReason.length > 0 && (
                        <div className="mt-2 rounded-2xl border border-amber-200 bg-white/70 px-3 py-2 text-[11px] font-mono text-amber-700">
                          Lý do kỹ thuật: {msg.refuseReason.join('; ')}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
              {msg.role === 'assistant' && !msg.isTyping && msg.degraded && !msg.unverified && msg.id !== 'welcome' && (
                <div className="w-full rounded-2xl border border-sky-200 bg-sky-50/80 px-4 py-3 text-sky-900 text-xs font-semibold leading-6">
                  Câu trả lời dùng căn cứ đã truy hồi từ kho số hóa (chế độ tóm lược / remap citation). Nên đối chiếu bản chính thức trước khi dùng chính thức.
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
        </div>
      </div>

      <form onSubmit={handleSend} className="border-t border-slate-200 bg-white/90 p-4 backdrop-blur sm:p-5">
        <div className="mx-auto flex max-w-5xl items-end gap-3 rounded-[24px] border border-slate-200 bg-slate-50 p-2 shadow-inner focus-within:border-blue-300 focus-within:ring-4 focus-within:ring-blue-100">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend(e);
              }
            }}
            rows={1}
            placeholder="Nhập tình huống pháp lý, câu hỏi hoặc số hiệu văn bản..."
            className="max-h-32 min-h-[52px] flex-1 resize-none bg-transparent px-4 py-3 text-sm font-medium text-slate-800 outline-none placeholder:text-slate-400"
          />
          <button type="submit" disabled={isLoading || !input.trim()} className="flex h-12 items-center gap-2 rounded-2xl bg-gradient-info px-5 text-sm font-black text-white shadow-lg shadow-blue-500/20 transition-all hover:-translate-y-0.5 hover:shadow-blue-500/30 disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50">
            Gửi <PaperPlaneRight size={18} weight="bold" />
          </button>
        </div>
        <p className="mx-auto mt-2 max-w-5xl text-[11px] font-medium text-slate-400">Enter để gửi, Shift + Enter để xuống dòng.</p>
      </form>
    </div>
  );
}
