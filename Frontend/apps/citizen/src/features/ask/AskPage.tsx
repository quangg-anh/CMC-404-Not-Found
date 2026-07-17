import { useState, useRef, useEffect } from 'react';
import { PaperPlaneRight, User, Robot, Scales, ShieldCheck, ArrowLeft, Trash, Lightbulb, WarningCircle } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { CitationCard } from '../../../../../packages/ui-legal/src/components/CitationCard';
import { GraphPathBreadcrumb } from '../../../../../packages/ui-legal/src/components/GraphPathBreadcrumb';

// Tương thích hoàn toàn với Contract API Backend (Mục 6.4 SYSTEM_BACKEND.md)
export interface BackendCitation {
  khoan_id?: string;
  quote: string;
  van_ban: string;
  dieu: string;
  score?: number;
}

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  citations?: BackendCitation[];
  graphPaths?: string[];
  confidence?: 'high' | 'medium' | 'low';
  isTyping?: boolean;
}

export default function AskPage() {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'ai',
      content: 'Chào bạn, tôi là Trợ lý Pháp lý ảo của Cổng Thông tin Pháp luật. Tôi có thể giúp bạn giải đáp các quy định pháp luật hiện hành dựa trên cơ sở dữ liệu chính thức. \n\nBạn cần hỏi về vấn đề gì?',
    }
  ]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    // Simulate AI typing
    const typingId = (Date.now() + 1).toString();
    setMessages(prev => [...prev, { id: typingId, role: 'ai', content: '', isTyping: true }]);

    // Demo: Mock backend API Call
    setTimeout(() => {
      setIsLoading(false);
      setMessages(prev => prev.map(msg => 
        msg.id === typingId 
        ? {
            id: typingId,
            role: 'ai',
            content: 'Theo quy định hiện hành, người điều khiển xe mô tô, xe gắn máy mà trong máu hoặc hơi thở có nồng độ cồn sẽ bị xử phạt hành chính từ 2.000.000 VNĐ đến 8.000.000 VNĐ tùy mức độ vi phạm, đồng thời tước quyền sử dụng Giấy phép lái xe từ 10 tháng đến 24 tháng.\n\nĐặc biệt với lỗi này, cơ quan chức năng có quyền tạm giữ phương tiện vi phạm lên đến 07 ngày làm việc để ngăn chặn hành vi vi phạm.',
            citations: [
              { van_ban: 'Nghị định 100/2019/NĐ-CP (Sửa đổi bởi NĐ 123/2021)', dieu: 'Điều 6, Khoản 6, Điểm c', quote: 'Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng đối với người điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn nhưng chưa vượt quá 50 miligam/100 mililít máu hoặc chưa vượt quá 0,25 miligam/1 lít khí thở.' },
              { van_ban: 'Nghị định 100/2019/NĐ-CP', dieu: 'Điều 82, Khoản 1', quote: 'Để ngăn chặn ngay vi phạm hành chính, người có thẩm quyền được phép tạm giữ phương tiện tối đa đến 07 ngày trước khi ra quyết định xử phạt đối với các hành vi vi phạm...' }
            ],
            confidence: 'high',
            graphPaths: [
              "Khoản 6 Điều 6 → QUY_DINH → Mức Phạt Nồng Độ Cồn",
              "Mức Phạt Nồng Độ Cồn → AP_DUNG_CHO → Người điều khiển mô tô",
              "Điều 82 → QUY_DINH → Tạm giữ phương tiện"
            ]
          }
        : msg
      ));
    }, 1800);
  };

  const handleSuggestion = (suggestion: string) => {
    setInput(suggestion);
    // Let the user click send themselves or auto-send. We will auto-send here.
    setTimeout(() => {
      const form = document.getElementById('chat-form') as HTMLFormElement;
      if (form) form.requestSubmit();
    }, 50);
  };

  return (
    <div className="flex flex-col h-screen bg-[#f8fafc] font-sans selection:bg-brand selection:text-white">
      {/* Header - Glassmorphism */}
      <header className="bg-white/80 backdrop-blur-xl border-b border-slate-200/80 shrink-0 z-20 sticky top-0">
        <div className="h-[72px] max-w-5xl mx-auto px-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-slate-500 hover:text-slate-900 transition-colors font-bold text-sm bg-slate-100 hover:bg-slate-200 px-4 py-2 rounded-full">
            <ArrowLeft size={16} weight="bold" /> Trang chủ
          </Link>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-brand to-red-800 rounded-xl flex items-center justify-center text-white shadow-md shadow-brand/20">
              <Scales size={22} weight="fill" />
            </div>
            <div className="flex flex-col">
              <h1 className="font-black text-slate-900 tracking-tight leading-tight">Trợ lý AI</h1>
              <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-widest flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span> Sẵn sàng
              </span>
            </div>
          </div>
          <button 
            onClick={() => setMessages([messages[0]])}
            className="flex items-center gap-2 text-slate-400 hover:text-red-600 hover:bg-red-50 transition-all font-bold text-sm px-4 py-2 rounded-full group"
          >
            <Trash size={16} weight="bold" className="group-hover:scale-110 transition-transform" /> <span className="hidden sm:inline">Xóa hội thoại</span>
          </button>
        </div>
      </header>

      {/* Chat Stream */}
      <main className="flex-1 overflow-y-auto p-4 sm:p-6 pb-40 scroll-smooth">
        <div className="max-w-4xl mx-auto space-y-8">
          {messages.map((msg, index) => (
            <div key={msg.id} className={`flex gap-3 sm:gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in-up`} style={{ animationDelay: `${index * 0.05}s` }}>
              {msg.role === 'ai' && (
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-2xl bg-gradient-to-br from-brandLight to-white flex items-center justify-center text-brand shrink-0 border border-brand/10 shadow-sm shadow-brand/5">
                  <Robot size={24} weight="fill" />
                </div>
              )}
              
              <div className={`max-w-[90%] sm:max-w-[80%] rounded-[24px] p-5 sm:p-6 ${
                msg.role === 'user' 
                  ? 'bg-gradient-to-br from-slate-800 to-slate-900 text-white shadow-xl shadow-slate-900/10 rounded-tr-[8px]' 
                  : 'bg-white border border-slate-200/60 shadow-lg shadow-slate-200/40 rounded-tl-[8px]'
              }`}>
                {msg.isTyping ? (
                  <div className="flex items-center gap-2 h-6 px-2">
                    <div className="w-2.5 h-2.5 bg-brand/40 rounded-full animate-bounce"></div>
                    <div className="w-2.5 h-2.5 bg-brand/60 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                    <div className="w-2.5 h-2.5 bg-brand/80 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                  </div>
                ) : (
                  <>
                    <p className={`text-[15px] sm:text-[16px] leading-relaxed whitespace-pre-wrap ${msg.role === 'user' ? 'font-medium' : 'font-normal text-slate-700'}`}>
                      {msg.content}
                    </p>
                    
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="mt-8 pt-6 border-t border-slate-100">
                        <div className="flex items-center gap-2 mb-4 text-xs font-bold text-emerald-600 uppercase tracking-widest bg-emerald-50 w-fit px-3 py-1.5 rounded-lg border border-emerald-100">
                          <ShieldCheck size={16} weight="fill" /> Đã xác thực căn cứ pháp lý
                        </div>
                        <div className="space-y-3">
                          {msg.citations.map((cit, idx) => (
                            <CitationCard key={idx} van_ban={cit.van_ban} dieu={cit.dieu} quote={cit.quote} khoan_id={cit.khoan_id} />
                          ))}
                        </div>
                      </div>
                    )}

                    {msg.graphPaths && (
                      <GraphPathBreadcrumb paths={msg.graphPaths} />
                    )}
                  </>
                )}
              </div>

              {msg.role === 'user' && (
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-2xl bg-slate-200 flex items-center justify-center text-slate-600 shrink-0 shadow-sm">
                  <User size={24} weight="fill" />
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} className="h-4" />
        </div>
      </main>

      {/* Input Box - Floating fixed at bottom */}
      <div className="fixed bottom-0 inset-x-0 bg-gradient-to-t from-[#f8fafc] via-[#f8fafc]/90 to-transparent pb-6 pt-12 px-4 z-20 pointer-events-none">
        <div className="max-w-4xl mx-auto pointer-events-auto">
          {messages.length === 1 && (
             <div className="flex flex-wrap gap-2 sm:gap-3 mb-6 justify-center">
               {["Mức phạt nồng độ cồn 2026?", "Quy định về nghỉ thai sản?", "Thủ tục làm CCCD gắn chip?"].map((suggestion, idx) => (
                 <button 
                   key={idx} 
                   onClick={() => handleSuggestion(suggestion)}
                   className="bg-white/80 backdrop-blur border border-slate-200/80 text-slate-700 px-5 py-2.5 rounded-full text-sm font-semibold hover:border-brand/50 hover:bg-brandLight hover:text-brand transition-all flex items-center gap-2 shadow-sm hover:shadow-md hover:-translate-y-0.5"
                 >
                   <Lightbulb size={16} weight="fill" className="text-amber-500" />
                   {suggestion}
                 </button>
               ))}
             </div>
          )}
          
          <form id="chat-form" onSubmit={handleSend} className="relative group shadow-2xl shadow-slate-200/50 rounded-[28px] flex items-end bg-white border border-slate-200/80 p-2 transition-all focus-within:border-brand/50 focus-within:ring-4 focus-within:ring-brand/10">
            <textarea 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Nhập câu hỏi pháp lý của bạn..."
              className="w-full bg-transparent text-slate-900 py-4 pl-6 pr-16 text-lg font-medium focus:outline-none resize-none max-h-32 min-h-[60px]"
              rows={1}
            />
            <button 
              type="submit"
              disabled={!input.trim()}
              className="absolute right-3 bottom-3 bg-brand hover:bg-red-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed text-white w-12 h-12 rounded-2xl flex items-center justify-center transition-all disabled:shadow-none shadow-lg shadow-brand/30 hover:scale-105 active:scale-95"
            >
              <PaperPlaneRight size={22} weight="fill" />
            </button>
          </form>
          
          <div className="text-center mt-4 flex items-center justify-center gap-1.5 opacity-60">
            <WarningCircle size={14} className="text-slate-500" />
            <span className="text-xs font-semibold text-slate-500">
              AI có thể trả lời không chính xác. Hãy luôn đối chiếu với Căn cứ pháp lý nguyên văn đính kèm.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
