import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  ChatCircleDots,
  PaperPlaneRight,
  Robot,
  SpinnerGap,
  X,
  ArrowsOut,
  WarningCircle,
} from '@phosphor-icons/react';
import { apiPost } from '../../lib/api';
import { SUGGESTIONS } from './CitizenChrome';
import { AnswerMarkdown } from '../../../../../packages/ui-legal/src/components/AnswerMarkdown';
import { CitationCard } from '../../../../../packages/ui-legal/src/components/CitationCard';
import { HonestyBanner } from '../../../../../packages/ui-legal/src/components/HonestyBanner';
import { normalizeQAResponse } from '../../lib/qaContract';
import type { NormalizedCitation } from '../../lib/qaContract';

type PanelMsg = {
  id: string;
  role: 'user' | 'ai';
  content: string;
  isError?: boolean;
  citations?: NormalizedCitation[];
  confidence?: 'high' | 'medium' | 'low';
  unverified?: boolean;
  degraded?: boolean;
  refused?: boolean;
  progressHint?: string;
};

const WELCOME: PanelMsg = {
  id: 'welcome',
  role: 'ai',
  content: 'Xin chào! Hỏi pháp luật bằng câu đơn giản — tôi sẽ trả lời kèm căn cứ khi có thể.',
};

const PROGRESS = [
  'Đang tra cứu điều khoản…',
  'Đang tổng hợp câu trả lời…',
  'Đang kiểm tra trích dẫn…',
];

/**
 * Floating chat bubble for the citizen landing shell.
 * Hidden on `/ask` (full-page chat already exists there).
 */
export function CitizenChatBubble() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<PanelMsg[]>([WELCOME]);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const hideOnAsk = pathname === '/ask' || pathname.startsWith('/ask/');

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => inputRef.current?.focus(), 80);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, open]);

  const send = useCallback(async (raw: string) => {
    const question = raw.trim();
    if (!question || loading) return;
    setLoading(true);
    setInput('');
    const userMsg: PanelMsg = { id: `u-${Date.now()}`, role: 'user', content: question };
    const typingId = `t-${Date.now()}`;
    setMessages((m) => [
      ...m,
      userMsg,
      { id: typingId, role: 'ai', content: '', progressHint: PROGRESS[0] },
    ]);

    let step = 0;
    const timer = window.setInterval(() => {
      step = Math.min(step + 1, PROGRESS.length - 1);
      setMessages((m) =>
        m.map((msg) => (msg.id === typingId ? { ...msg, progressHint: PROGRESS[step] } : msg)),
      );
    }, 2000);

    try {
      const rawResponse = await apiPost<unknown>('/citizen/qa/ask', { question });
      const data = normalizeQAResponse(rawResponse);
      const answer = data.answer || 'Không nhận được câu trả lời.';
      const citations = data.citations;
      setMessages((m) =>
        m.map((msg) =>
          msg.id === typingId
            ? {
                id: `a-${Date.now()}`,
                role: 'ai',
                content: answer,
                citations,
                confidence: data.confidence,
                unverified: data.unverified,
                degraded: data.degraded,
                refused: data.refused,
              }
            : msg,
        ),
      );
    } catch (err) {
      setMessages((m) =>
        m.map((msg) =>
          msg.id === typingId
            ? {
                id: `e-${Date.now()}`,
                role: 'ai',
                isError: true,
                unverified: true,
                confidence: 'low',
                content: err instanceof Error ? err.message : 'Không kết nối được trợ lý. Thử lại sau.',
              }
            : msg,
        ),
      );
    } finally {
      window.clearInterval(timer);
      setLoading(false);
    }
  }, [loading]);

  if (hideOnAsk) return null;

  return (
    <div className="ls-chat-fab pointer-events-none fixed bottom-5 right-5 z-[60] flex flex-col items-end gap-3 sm:bottom-6 sm:right-6">
      {open ? (
        <section
          className="ls-chat-panel pointer-events-auto flex w-[min(100vw-1.5rem,380px)] flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_24px_64px_-20px_rgba(15,23,42,0.45),0_0_0_1px_rgba(37,87,214,0.08)]"
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
        >
          <header className="flex items-center gap-3 border-b border-slate-100 bg-gradient-to-r from-[#1E3A8A] via-[#2557D6] to-[#3B6FE8] px-4 py-3 text-white">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15">
              <Robot size={20} weight="fill" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <h2 id={titleId} className="truncate text-sm font-extrabold tracking-tight">
                Trợ lý pháp lý
              </h2>
              <p className="text-[11px] font-medium text-sky-100/90">LexSocial AI · có căn cứ</p>
            </div>
            <button
              type="button"
              className="rounded-lg p-1.5 text-white/90 transition hover:bg-white/15"
              aria-label="Mở trang hỏi đầy đủ"
              title="Mở trang hỏi đầy đủ"
              onClick={() => {
                setOpen(false);
                navigate('/ask');
              }}
            >
              <ArrowsOut size={18} weight="bold" />
            </button>
            <button
              type="button"
              className="rounded-lg p-1.5 text-white/90 transition hover:bg-white/15"
              aria-label="Đóng chat"
              onClick={() => setOpen(false)}
            >
              <X size={18} weight="bold" />
            </button>
          </header>

          <div ref={listRef} className="ls-chat-panel__body flex max-h-[min(52vh,420px)] min-h-[220px] flex-col gap-3 overflow-y-auto bg-[#F1F5F9] p-3">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[92%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-sm ${
                    msg.role === 'user'
                      ? 'rounded-br-md bg-[#2557D6] text-white'
                      : msg.isError
                        ? 'rounded-bl-md border border-amber-200 bg-amber-50 text-amber-950'
                        : 'rounded-bl-md border border-slate-200/80 bg-white text-slate-800'
                  }`}
                >
                  {msg.progressHint && !msg.content ? (
                    <div className="inline-flex items-center gap-2 text-xs font-semibold text-slate-500">
                      <SpinnerGap size={14} className="animate-spin" weight="bold" /> {msg.progressHint}
                    </div>
                  ) : msg.role === 'ai' ? (
                    <>
                      <AnswerMarkdown content={msg.content} density="compact" />
                      <HonestyBanner
                        unverified={msg.unverified}
                        degraded={msg.degraded}
                        refused={msg.refused}
                        confidence={msg.confidence}
                        citationCount={msg.citations?.length ?? 0}
                      />
                      {msg.citations && msg.citations.length > 0 ? (
                        <div className="mt-2 space-y-2 border-t border-slate-100 pt-2">
                          {msg.citations.slice(0, 3).map((cit, idx) => (
                            <CitationCard
                              key={cit.citationId ?? cit.nodeId ?? idx}
                              van_ban={cit.documentNumber}
                              document_number={cit.documentNumber}
                              dieu={cit.article ? `Điều ${cit.article}` : ''}
                              article={cit.article}
                              clause={cit.clause}
                              point={cit.point}
                              quote={cit.quote}
                              khoan_id={cit.khoanId}
                              node_id={cit.nodeId}
                              lineage_id={cit.lineageId}
                              level={cit.level}
                              effective_from={cit.effectiveFrom}
                              effective_to={cit.effectiveTo}
                              as_of={cit.asOf}
                              support_status={cit.supportStatus}
                              entailment_score={cit.entailmentScore}
                              validation_source={cit.validationSource}
                              supports_claim_ids={cit.supportsClaimIds}
                            />
                          ))}
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  )}
                </div>
              </div>
            ))}
          </div>

          {messages.length <= 1 && !loading ? (
            <div className="flex flex-wrap gap-1.5 border-t border-slate-100 bg-white px-3 py-2">
              {SUGGESTIONS.slice(0, 2).map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => void send(q)}
                  className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-800"
                >
                  {q}
                </button>
              ))}
            </div>
          ) : null}

          <form
            className="flex items-end gap-2 border-t border-slate-200 bg-white p-3"
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              rows={1}
              disabled={loading}
              placeholder="Nhập câu hỏi…"
              aria-label="Nhập câu hỏi pháp lý"
              className="max-h-24 min-h-[44px] flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-medium text-slate-900 placeholder:text-slate-400 focus:border-blue-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#2557D6] text-white shadow-md transition hover:bg-[#1E46B8] disabled:cursor-not-allowed disabled:bg-slate-300"
              aria-label="Gửi"
            >
              {loading ? <SpinnerGap size={20} className="animate-spin" /> : <PaperPlaneRight size={20} weight="fill" />}
            </button>
          </form>

          <p className="flex items-center justify-center gap-1 bg-slate-50 px-3 pb-2.5 text-[10px] font-medium text-slate-500">
            <WarningCircle size={12} aria-hidden />
            Tham khảo ·{' '}
            <Link to="/ask" className="font-bold text-blue-700 hover:underline" onClick={() => setOpen(false)}>
              mở trang đầy đủ
            </Link>
          </p>
        </section>
      ) : null}

      <button
        type="button"
        className="ls-chat-fab__btn pointer-events-auto group relative flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-[#1E3A8A] via-[#2557D6] to-[#E85D0F] text-white shadow-[0_14px_36px_-10px_rgba(37,87,214,0.75)] transition hover:scale-105 hover:shadow-[0_18px_40px_-10px_rgba(37,87,214,0.85)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-300/50"
        aria-expanded={open}
        aria-label={open ? 'Đóng trợ lý chat' : 'Mở trợ lý chat pháp lý'}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="ls-chat-fab__ping absolute inset-0 rounded-full bg-blue-400/40" aria-hidden />
        {open ? <X size={26} weight="bold" /> : <ChatCircleDots size={28} weight="fill" />}
      </button>
    </div>
  );
}
