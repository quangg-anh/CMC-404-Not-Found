import { useState } from 'react';
import { PaperPlaneRight, User, Robot, ShieldCheck, WarningCircle } from '@phosphor-icons/react';
import { CitationCard } from '../../../../../packages/ui-legal/src/components/CitationCard';
import { apiPost } from '../../lib/api';

interface BackendCitation {
  khoan_id?: string;
  quote: string;
  van_ban: string;
  dieu: string;
  score?: number;
}

interface QAResponse {
  answer: string;
  citations: BackendCitation[];
  graph_paths: string[];
  confidence: 'high' | 'medium' | 'low';
  refuse_reason?: string[];
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: BackendCitation[];
  confidence?: 'high' | 'medium' | 'low';
  isTyping?: boolean;
}

export default function QAAdminPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 'welcome', role: 'assistant', content: 'Chào bạn, tôi là trợ lý LexSocial. Tôi trả lời các quy định pháp luật dựa trên dữ liệu đã số hóa, luôn kèm trích dẫn nguyên văn.' },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = input.trim();
    if (!question || isLoading) return;

    setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'user', content: question }]);
    setInput('');
    setIsLoading(true);

    const typingId = (Date.now() + 1).toString();
    setMessages((prev) => [...prev, { id: typingId, role: 'assistant', content: '', isTyping: true }]);

    try {
      const data = await apiPost<QAResponse>('/admin/qa/ask', { question, graph_paths_enabled: true, audience: 'admin' });
      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? { id: typingId, role: 'assistant', content: data.answer, citations: data.citations ?? [], confidence: data.confidence }
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
    <div className="max-w-4xl mx-auto h-[85vh] flex flex-col bg-surface rounded-2xl overflow-hidden shadow-card">
      <header className="p-6 border-b border-border bg-surface flex items-center justify-between z-10 shadow-sm relative">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-info"></div>
        <div>
          <h2 className="text-xl font-bold text-primary flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-info flex items-center justify-center text-white shadow-md">
              <Robot size={24} weight="fill" />
            </div>
            QA Bot (Kiểm thử Nội bộ)
          </h2>
          <p className="text-xs text-muted mt-2 font-medium">Bắt buộc trích dẫn (Evidence over answer)</p>
        </div>
      </header>

      <div className="flex-1 p-8 overflow-y-auto space-y-8 bg-background">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-4 max-w-[85%] ${msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`}>
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 shadow-md ${msg.role === 'user' ? 'bg-gradient-dark text-white' : 'bg-gradient-info text-white'}`}>
              {msg.role === 'user' ? <User size={20} weight="fill" /> : <Robot size={20} weight="fill" />}
            </div>
            <div className={`space-y-4 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`p-5 rounded-2xl text-sm font-medium shadow-soft whitespace-pre-wrap ${msg.role === 'user' ? 'bg-primary text-white rounded-tr-none' : 'bg-surface text-primary rounded-tl-none border border-border'}`}>
                {msg.isTyping ? (
                  <div className="flex items-center gap-1.5 h-5">
                    <span className="w-2 h-2 rounded-full bg-secondaryAccent/50 animate-bounce"></span>
                    <span className="w-2 h-2 rounded-full bg-secondaryAccent/70 animate-bounce [animation-delay:-0.15s]"></span>
                    <span className="w-2 h-2 rounded-full bg-secondaryAccent/90 animate-bounce [animation-delay:-0.3s]"></span>
                  </div>
                ) : (
                  msg.content
                )}
              </div>
              {msg.citations && msg.citations.length > 0 && (
                <div className="w-[500px] space-y-3">
                  <div className="flex items-center gap-2 text-xs font-bold text-emerald-600 uppercase tracking-widest">
                    <ShieldCheck size={16} weight="fill" /> Căn cứ pháp lý đã xác thực
                  </div>
                  {msg.citations.map((cit, idx) => (
                    <CitationCard key={idx} van_ban={cit.van_ban} dieu={cit.dieu} quote={cit.quote} khoan_id={cit.khoan_id} />
                  ))}
                </div>
              )}
              {msg.role === 'assistant' && !msg.isTyping && (!msg.citations || msg.citations.length === 0) && msg.id !== 'welcome' && (
                <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-600">
                  <WarningCircle size={14} weight="fill" /> Không có căn cứ nào được xác thực cho câu trả lời này.
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={handleSend} className="p-6 bg-surface border-t border-border flex gap-4">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Nhập tình huống pháp lý..."
          className="flex-1 bg-background border border-border text-primary rounded-xl px-5 py-4 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-secondaryAccent/30 focus:border-secondaryAccent transition-all shadow-inner"
        />
        <button type="submit" disabled={isLoading || !input.trim()} className="bg-gradient-accent text-white px-8 py-4 rounded-xl hover:shadow-lg transition-all flex items-center gap-2 font-bold disabled:opacity-50 disabled:cursor-not-allowed">
          Gửi <PaperPlaneRight size={18} weight="bold" />
        </button>
      </form>
    </div>
  );
}
