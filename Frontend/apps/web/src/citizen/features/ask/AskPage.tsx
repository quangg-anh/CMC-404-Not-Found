import { useState, useRef, useEffect, useCallback } from 'react';
import {
  PaperPlaneRight,
  User,
  Robot,
  ShieldCheck,
  Trash,
  WarningCircle,
  CalendarBlank,
  ArrowSquareOut,
  ArrowLeft,
  ArrowsClockwise,
  SpinnerGap,
} from '@phosphor-icons/react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { CitationCard } from '../../../../../../packages/ui-legal/src/components/CitationCard';
import { GraphPathBreadcrumb } from '../../../../../../packages/ui-legal/src/components/GraphPathBreadcrumb';
import { AnswerMarkdown } from '../../../../../../packages/ui-legal/src/components/AnswerMarkdown';
import { HonestyBanner } from '../../../../../../packages/ui-legal/src/components/HonestyBanner';
import { apiPost } from '../../../lib/api';
import { CitizenHeader, SuggestionChips } from '../../components/CitizenChrome';
import { AiTypingIndicator } from '../../components/AiTypingIndicator';
import { Atmosphere } from '../../components/Atmosphere';
import { LegalHistoryPanel } from '../../../components/LegalHistoryPanel';
import { normalizeQAResponse } from '../../../lib/qaContract';
import type { NormalizedCitation } from '../../../lib/qaContract';

type GraphPath = unknown;

interface ChangeNotice {
  khoan_van_ban?: string;
  thay_the_boi?: string;
  tu_ngay: string;
  message: string;
}

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  citations?: NormalizedCitation[];
  graphPaths?: GraphPath[];
  confidence?: 'high' | 'medium' | 'low';
  isTyping?: boolean;
  isError?: boolean;
  asOf?: string;
  notices?: ChangeNotice[];
  unverified?: boolean;
  degraded?: boolean;
  refused?: boolean;
  refusalMessage?: string;
  reasonCode?: string;
  contractVersion?: 'v1' | 'v2';
  progressHint?: string;
}

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  role: 'ai',
  content:
    'Xin chào! Tôi là trợ lý pháp lý của LexSocial AI.\n\nBạn có thể hỏi bằng câu đơn giản, ví dụ: “Nghỉ thai sản được bao nhiêu ngày?”\n\nTôi sẽ trả lời kèm căn cứ pháp lý để bạn dễ kiểm tra.',
};

export default function AskPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [isTypingComplete, setIsTypingComplete] = useState<Record<string, boolean>>({});
  const [lastFailedQuestion, setLastFailedQuestion] = useState<string | null>(null);
  const [historyCitation, setHistoryCitation] = useState<NormalizedCitation | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isLoadingRef = useRef(false);
  const asOfRef = useRef(asOf);
  const autoSentRef = useRef(false);

  useEffect(() => {
    asOfRef.current = asOf;
  }, [asOf]);

  const scrollToBottom = () => {
    const el = mainRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  };

  useEffect(() => {
    resizeTextarea();
  }, [input]);

  const sendQuestion = useCallback(async (rawQuestion: string) => {
    const question = rawQuestion.trim();
    if (!question || isLoadingRef.current) return;

    isLoadingRef.current = true;
    setIsLoading(true);
    setInput('');
    setLastFailedQuestion(null);

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: question };
    const typingId = (Date.now() + 1).toString();
    const progressSteps = [
      'Đang tra cứu điều khoản…',
      'Đang tổng hợp câu trả lời…',
      'Đang kiểm tra trích dẫn…',
    ];
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: typingId, role: 'ai', content: '', isTyping: true, progressHint: progressSteps[0] },
    ]);

    let step = 0;
    const progressTimer = window.setInterval(() => {
      step = Math.min(step + 1, progressSteps.length - 1);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === typingId && msg.isTyping
            ? { ...msg, progressHint: progressSteps[step] }
            : msg,
        ),
      );
    }, 2200);

    const asOfVal = asOfRef.current;
    try {
      const payload: { question: string; as_of?: string } = { question };
      if (asOfVal) payload.as_of = asOfVal;
      const raw = await apiPost<unknown>('/citizen/qa/ask', payload);
      const data = normalizeQAResponse(raw, asOfVal);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === typingId
            ? {
                id: typingId,
                role: 'ai',
                content: data.answer,
                citations: data.citations ?? [],
                graphPaths: data.graphPaths,
                confidence: data.confidence,
                asOf: data.asOf ?? asOfVal,
                notices: data.notices as ChangeNotice[],
                unverified: data.unverified,
                degraded: data.degraded,
                refused: data.refused,
                refusalMessage: data.refusalMessage,
                reasonCode: data.reasonCode,
                contractVersion: data.contractVersion,
              }
            : msg,
        ),
      );
      setIsTypingComplete((prev) => ({ ...prev, [typingId]: true }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Lỗi không xác định';
      setLastFailedQuestion(question);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === typingId
            ? {
                id: typingId,
                role: 'ai',
                content: `Không kết nối được trợ lý lúc này (${message}). Bạn có thể thử gửi lại.`,
                confidence: 'low',
                isError: true,
                unverified: true,
              }
            : msg,
        ),
      );
      setIsTypingComplete((prev) => ({ ...prev, [typingId]: true }));
    } finally {
      window.clearInterval(progressTimer);
      isLoadingRef.current = false;
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const q = searchParams.get('q')?.trim();
    if (!q || autoSentRef.current) return;
    autoSentRef.current = true;
    navigate('/ask', { replace: true });
    void sendQuestion(q);
  }, [searchParams, navigate, sendQuestion]);

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    await sendQuestion(input);
  };

  const clearChat = () => {
    setMessages([WELCOME_MESSAGE]);
    setIsTypingComplete({});
    setInput('');
    setLastFailedQuestion(null);
  };

  const showSuggestions = messages.length <= 1 && !isLoading;

  return (
    <div className="relative flex h-[100dvh] flex-col overflow-hidden bg-[#E8EEF8]">
      <Atmosphere tone="chat" />
      <CitizenHeader />

      <div className="relative z-[1] mx-auto flex w-full max-w-chat flex-1 flex-col overflow-hidden px-3 pb-3 pt-2 sm:px-5 sm:pb-4">
        <div className="ls-chat-stage flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_20px_50px_-28px_rgba(15,23,42,0.45)]">
        {/* Chat toolbar / metadata — asOf lives here, NOT on the composer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-white px-3 py-3 sm:px-4">
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/" className="ls-btn-secondary !min-h-[40px] !px-3 !text-sm">
              <ArrowLeft size={16} weight="bold" aria-hidden /> Trang chủ
            </Link>
            {isLoading ? (
              <span className="inline-flex items-center gap-2 rounded-control bg-primary-soft px-3 py-2 text-sm font-semibold text-primary">
                <SpinnerGap size={16} className="animate-spin" weight="bold" aria-hidden />
                Đang trả lời…
              </span>
            ) : (
              <span className="inline-flex items-center gap-2 rounded-control bg-success-soft px-3 py-2 text-sm font-semibold text-success">
                <span className="ls-pulse-dot h-2 w-2 rounded-full bg-success" aria-hidden />
                Sẵn sàng trả lời
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex min-h-[40px] items-center gap-2 rounded-control border border-border bg-white/90 px-3 text-sm font-semibold text-ink shadow-sm backdrop-blur-sm transition duration-ui hover:border-primary/30">
              <CalendarBlank size={16} className="text-primary" weight="bold" aria-hidden />
              Ngày áp dụng
              <input
                type="date"
                value={asOf}
                onChange={(e) => setAsOf(e.target.value)}
                className="bg-transparent font-semibold text-ink outline-none"
                aria-label="Ngày áp dụng pháp luật"
              />
            </label>
            <button type="button" onClick={clearChat} className="ls-btn-danger !min-h-[40px] !px-3 !text-sm" aria-label="Xóa hội thoại">
              <Trash size={16} weight="bold" aria-hidden />
              Xóa chat
            </button>
          </div>
        </div>

        <main
          id="main"
          ref={mainRef}
          className="flex-1 overflow-y-auto bg-[#F4F7FC] px-3 py-5 sm:px-5"
          aria-live="polite"
        >
          <div className="mx-auto flex w-full flex-col gap-5">
            {messages.map((msg) => (
              <div key={msg.id} className={`ls-msg-in flex w-full gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.role === 'ai' && (
                  <div
                    className={`relative mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-primary-soft to-[#D9E4FB] text-primary shadow-sm ${msg.isTyping ? 'ls-avatar-thinking' : ''}`}
                    aria-hidden
                  >
                    <Robot size={22} weight="fill" />
                    {msg.isTyping ? <span className="ls-typing-ring" /> : null}
                  </div>
                )}

                <div
                  className={`min-w-0 rounded-card px-4 py-4 sm:px-5 ${
                    msg.role === 'user'
                      ? 'w-fit max-w-[84%] rounded-tr-md bg-[#2557D6] text-white shadow-md sm:max-w-[72%]'
                      : msg.isTyping
                        ? 'w-fit max-w-[calc(100%-3.25rem)] rounded-tl-md border border-primary/30 bg-white shadow-[0_8px_24px_-12px_rgba(37,87,214,0.35)] sm:max-w-[88%]'
                        : 'w-fit max-w-[calc(100%-3.25rem)] rounded-tl-md border border-slate-200 bg-white shadow-sm sm:max-w-[88%]'
                  }`}
                >
                  {msg.isTyping ? (
                    <div className="space-y-2">
                      <AiTypingIndicator />
                      {msg.progressHint ? (
                        <p className="text-xs font-semibold text-slate-500">{msg.progressHint}</p>
                      ) : null}
                    </div>
                  ) : (
                    <div className={msg.role === 'ai' ? 'ls-answer-in' : undefined}>
                      {msg.role === 'ai' ? (
                        <div className="text-[15px] leading-relaxed sm:text-base">
                          <AnswerMarkdown content={msg.content} />
                        </div>
                      ) : (
                        <p className="whitespace-pre-wrap text-[15px] font-semibold leading-relaxed sm:text-base">{msg.content}</p>
                      )}

                      {msg.role === 'ai' && (
                        <HonestyBanner
                          unverified={msg.unverified}
                          degraded={msg.degraded}
                          refused={msg.refused}
                          confidence={msg.confidence}
                          citationCount={msg.citations?.length ?? 0}
                        />
                      )}

                      {msg.role === 'ai' && msg.refused && msg.refusalMessage && (
                        <div className="mt-3 rounded-control border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                          <p className="font-bold">Câu trả lời đã được chặn để tránh cung cấp thông tin không có căn cứ.</p>
                          <p className="mt-1 leading-relaxed">{msg.refusalMessage}</p>
                          {msg.reasonCode ? <p className="mt-2 text-[11px] font-mono text-amber-700">Mã: {msg.reasonCode}</p> : null}
                        </div>
                      )}

                      {msg.role === 'ai' && msg.asOf && (                        <div className="mt-3 inline-flex items-center gap-2 rounded-control bg-background px-3 py-1.5 text-sm font-semibold text-muted">
                          <CalendarBlank size={16} weight="bold" aria-hidden />
                          Ngày áp dụng: {new Date(`${msg.asOf}T00:00:00`).toLocaleDateString('vi-VN')}
                        </div>
                      )}

                      {msg.isError && lastFailedQuestion && (
                        <button
                          type="button"
                          className="ls-btn-primary mt-4 !min-h-[44px] !text-sm"
                          onClick={() => void sendQuestion(lastFailedQuestion)}
                        >
                          <ArrowsClockwise size={16} weight="bold" aria-hidden />
                          Thử lại
                        </button>
                      )}

                      {msg.notices?.map((notice, idx) => (
                        <div key={`${notice.tu_ngay}-${idx}`} className="mt-3 rounded-control border border-warning/25 bg-warning-soft p-3 text-warning">
                          <div className="flex gap-2">
                            <WarningCircle size={20} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
                            <div>
                              <p className="text-sm font-bold">
                                Quy định đổi từ {new Date(`${notice.tu_ngay}T00:00:00`).toLocaleDateString('vi-VN')}
                              </p>
                              <p className="mt-1 text-sm leading-relaxed opacity-90">{notice.message}</p>
                              <a
                                href="/admin/diff"
                                target="_blank"
                                rel="noreferrer"
                                className="mt-2 inline-flex items-center gap-1 text-sm font-bold underline"
                              >
                                Xem thay đổi <ArrowSquareOut size={14} weight="bold" aria-hidden />
                              </a>
                            </div>
                          </div>
                        </div>
                      ))}

                      {msg.citations &&
                        msg.citations.length > 0 &&
                        (isTypingComplete[msg.id] || msg.id === 'welcome') && (
                          <div className="mt-4 border-t border-border pt-4">
                            <div className="mb-3 inline-flex items-center gap-2 rounded-control bg-success-soft px-3 py-1.5 text-sm font-bold text-success">
                              <ShieldCheck size={16} weight="fill" aria-hidden /> Căn cứ pháp lý
                            </div>
                            <div className="space-y-3">
                              {msg.citations.map((cit, idx) => (
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
                                  onOpenTimeline={cit.nodeId || cit.lineageId ? () => setHistoryCitation(cit) : undefined}
                                />
                              ))}
                            </div>
                          </div>
                        )}

                      {msg.graphPaths && (isTypingComplete[msg.id] || msg.id === 'welcome') && (
                        <div className="mt-3">
                          <GraphPathBreadcrumb paths={msg.graphPaths} />
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {msg.role === 'user' && (
                  <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-border/60 text-muted" aria-hidden>
                    <User size={22} weight="fill" />
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} className="h-2" />
          </div>
        </main>

        {/* Sticky composer */}
        <div className="sticky bottom-0 border-t border-slate-200 bg-white px-3 pb-3 pt-3 sm:px-4">
          {showSuggestions && (
            <div className="ls-reveal mb-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Gợi ý câu hỏi</p>
              <SuggestionChips onSelect={(q) => void sendQuestion(q)} />
            </div>
          )}

          <form
            id="chat-form"
            onSubmit={handleSend}
            className={`ls-search-shell flex items-end gap-2 !border-slate-200 !bg-slate-50 !p-2 !shadow-none ${isLoading ? 'ls-composer-busy' : ''}`}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
              placeholder="Gõ câu hỏi của bạn…"
              rows={1}
              disabled={isLoading}
              aria-label="Ô nhập câu hỏi"
              className="max-h-[140px] min-h-[48px] w-full resize-none bg-transparent px-3 py-3 text-base font-medium text-ink placeholder:text-muted/80 focus:outline-none disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-control bg-primary text-white shadow-[0_8px_18px_-10px_rgba(37,87,214,0.7)] transition duration-ui hover:-translate-y-0.5 hover:bg-primary-hover disabled:translate-y-0 disabled:cursor-not-allowed disabled:bg-border disabled:text-muted disabled:shadow-none"
              aria-label={isLoading ? 'Đang gửi…' : 'Gửi câu hỏi'}
            >
              {isLoading ? (
                <SpinnerGap size={22} className="animate-spin" weight="bold" aria-hidden />
              ) : (
                <PaperPlaneRight size={22} weight="fill" aria-hidden />
              )}
            </button>
          </form>

          <p className="mt-2 flex items-start justify-center gap-1.5 text-center text-xs text-muted sm:text-sm">
            <WarningCircle size={14} className="mt-0.5 shrink-0" aria-hidden />
            AI có thể sai. Hãy đọc phần căn cứ pháp lý và đối chiếu văn bản gốc khi cần.
          </p>
        </div>
        </div>
      </div>
      <LegalHistoryPanel
        citation={historyCitation}
        audience="citizen"
        onClose={() => setHistoryCitation(null)}
      />
    </div>
  );
}
