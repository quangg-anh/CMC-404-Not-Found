import { Link, useNavigate } from 'react-router-dom';
import { MagnifyingGlass, BookOpen, Article, Scales, ArrowRight, Sparkle, Clock, ShieldCheck, LockKey, Gavel } from '@phosphor-icons/react';

function Header() {
  return (
    <header className="fixed top-0 inset-x-0 bg-white/80 backdrop-blur-lg border-b border-slate-200/80 z-50 transition-all duration-300">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-11 h-11 bg-gradient-to-br from-brand to-red-900 rounded-xl flex items-center justify-center text-white shadow-lg shadow-brand/20 group-hover:scale-105 transition-transform duration-300">
            <Scales size={26} weight="fill" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight leading-none group-hover:text-brand transition-colors">LexSocial<span className="text-brand">AI</span></h1>
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-1 block">Cổng thông tin pháp luật</span>
          </div>
        </Link>
        <nav className="hidden md:flex items-center gap-1">
          <Link to="/" className="px-4 py-2 rounded-full text-sm font-bold text-brand bg-brandLight flex items-center gap-2 transition-colors">
            <MagnifyingGlass size={18} weight="bold" /> Trợ lý Pháp lý
          </Link>
          <Link to="/news" className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 flex items-center gap-2 transition-all">
            <Article size={18} /> Tin tức
          </Link>
          <Link to="/van-ban" className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 flex items-center gap-2 transition-all">
            <BookOpen size={18} /> Văn bản
          </Link>
          <div className="w-px h-6 bg-slate-200 mx-2"></div>
          <Link to="/login" className="px-5 py-2 rounded-full text-sm font-bold text-white bg-slate-900 hover:bg-slate-800 transition-all shadow-md hover:shadow-lg">
            Đăng nhập
          </Link>
        </nav>
      </div>
    </header>
  );
}

function HeroSection() {
  const navigate = useNavigate();

  return (
    <div className="relative overflow-hidden bg-[#0f172a] min-h-screen flex items-center justify-center pt-20 selection:bg-brand selection:text-white">
      {/* Premium Dark Background Effects */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[20%] left-[10%] w-[60%] h-[60%] rounded-full bg-brand/20 blur-[120px] mix-blend-screen" />
        <div className="absolute top-[20%] right-[5%] w-[40%] h-[40%] rounded-full bg-blue-600/10 blur-[100px] mix-blend-screen" />
        {/* Subtle grid pattern */}
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wMykiLz48L3N2Zz4=')] [mask-image:linear-gradient(to_bottom,white_20%,transparent_80%)]" />
      </div>

      <div className="max-w-4xl w-full mx-auto px-4 sm:px-6 relative z-10 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-white/90 text-sm font-semibold mb-8 backdrop-blur-md shadow-2xl hover:bg-white/10 transition-colors cursor-default">
          <Sparkle size={16} weight="fill" className="text-red-400" />
          <span>Phiên bản thử nghiệm AI 2026</span>
        </div>
        
        <h2 className="text-5xl sm:text-7xl font-extrabold text-white tracking-tight mb-6 leading-[1.1]">
          Tra cứu pháp luật <br className="hidden sm:block" />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-red-400 via-brand to-orange-500">
            nhanh chóng & chính xác
          </span>
        </h2>
        
        <p className="text-lg sm:text-xl text-slate-300 mb-12 max-w-2xl mx-auto leading-relaxed font-medium">
          Hệ thống Trợ lý Ảo AI giải đáp thắc mắc dựa trên cơ sở dữ liệu chính thức, luôn đính kèm <strong className="text-white">Căn cứ pháp lý nguyên văn</strong>.
        </p>
        
        <div className="relative max-w-3xl mx-auto group">
          <div className="absolute inset-0 bg-gradient-to-r from-brand/20 to-red-500/20 rounded-3xl blur-xl group-focus-within:blur-2xl transition-all duration-500 opacity-50 group-hover:opacity-100"></div>
          <div className="relative flex items-center bg-white/10 backdrop-blur-2xl border border-white/20 rounded-3xl p-2 shadow-2xl transition-all focus-within:bg-white/15 focus-within:border-brand/50">
            <div className="pl-4 pr-2 flex items-center pointer-events-none">
              <MagnifyingGlass size={24} className="text-slate-400 group-focus-within:text-brandLight transition-colors" />
            </div>
            <input 
              type="text" 
              placeholder="Ví dụ: Quy định thai sản cho lao động nam 2026?"
              className="flex-1 bg-transparent border-none text-white placeholder:text-slate-400 text-lg sm:text-xl font-medium focus:outline-none py-4 px-2 w-full"
            />
            <button 
              onClick={() => navigate('/ask')}
              className="bg-brand hover:bg-red-600 text-white font-bold py-4 px-6 sm:px-8 rounded-2xl transition-all duration-300 shadow-lg hover:shadow-brand/40 flex items-center gap-2 hover:scale-[1.02] active:scale-95 shrink-0"
            >
              <span className="hidden sm:inline">Hỏi AI</span>
              <ArrowRight size={18} weight="bold" />
            </button>
          </div>
        </div>

        <div className="mt-14 flex flex-wrap items-center justify-center gap-x-10 gap-y-4 text-sm text-slate-400 font-medium">
          <span className="flex items-center gap-2"><ShieldCheck size={20} className="text-emerald-400" /> Nguồn dữ liệu chính thống</span>
          <span className="flex items-center gap-2"><Clock size={20} className="text-sky-400" /> Cập nhật thời gian thực</span>
          <span className="flex items-center gap-2"><LockKey size={20} className="text-purple-400" /> Bảo mật thông tin</span>
        </div>
      </div>
    </div>
  );
}

function NewsHighlight() {
  const news = [
    { id: 1, title: 'Hướng dẫn mới về xử phạt vi phạm giao thông nội đô áp dụng từ T7/2026', type: 'Giao thông', time: '2 giờ trước', readTime: '3 phút đọc', icon: <Gavel size={24} className="text-brand" /> },
    { id: 2, title: 'Quy định quản lý dữ liệu cá nhân trên các nền tảng mạng xã hội xuyên biên giới', type: 'Công nghệ', time: '5 giờ trước', readTime: '5 phút đọc', icon: <LockKey size={24} className="text-blue-600" /> },
    { id: 3, title: 'Thay đổi về mức đóng BHXH tự nguyện áp dụng cho người lao động tự do', type: 'Lao động', time: '1 ngày trước', readTime: '4 phút đọc', icon: <ShieldCheck size={24} className="text-emerald-600" /> },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 relative z-20">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-12 px-2 gap-4">
        <div>
          <h3 className="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">
            Điểm tin Pháp luật
          </h3>
          <p className="text-slate-500 font-medium mt-2 text-lg">Các văn bản và chính sách mới nhất vừa được ban hành</p>
        </div>
        <Link to="/news" className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold rounded-full transition-colors group">
          Xem tất cả <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
        {news.map((item) => (
          <div key={item.id} className="group bg-white rounded-3xl p-1 shadow-sm hover:shadow-xl hover:shadow-brand/5 border border-slate-200/60 transition-all duration-300 hover:-translate-y-1 cursor-pointer">
            <div className="h-full bg-white rounded-[22px] p-6 sm:p-8 flex flex-col justify-between relative overflow-hidden border border-transparent group-hover:border-slate-100 transition-colors">
              
              <div className="absolute top-0 left-0 w-full h-1.5 bg-gradient-to-r from-transparent via-brand to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              
              <div>
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-slate-50 flex items-center justify-center border border-slate-100 group-hover:scale-110 transition-transform duration-300">
                      {item.icon}
                    </div>
                    <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                      {item.type}
                    </span>
                  </div>
                  <span className="text-xs font-semibold text-slate-400 flex items-center gap-1 bg-slate-50 px-2.5 py-1 rounded-md">
                    <Clock size={14} /> {item.time}
                  </span>
                </div>
                <h4 className="text-xl font-bold text-slate-800 leading-snug group-hover:text-brand transition-colors duration-300 line-clamp-3">
                  {item.title}
                </h4>
              </div>
              
              <div className="mt-8 pt-5 border-t border-slate-100 flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-400">
                  {item.readTime}
                </span>
                <div className="flex items-center text-sm font-bold text-brand opacity-0 -translate-x-4 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300">
                  Đọc tóm tắt <ArrowRight size={16} className="ml-1" />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Header />
      <main className="flex-1">
        <HeroSection />
        <NewsHighlight />
      </main>
      <footer className="bg-white border-t border-slate-200 py-12 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3 opacity-50 hover:opacity-100 transition-opacity cursor-pointer">
            <Scales size={24} weight="fill" className="text-slate-400" />
            <span className="text-lg font-black text-slate-400 tracking-tight">LexSocial</span>
          </div>
          <div className="text-center md:text-right text-slate-500 text-sm font-medium">
            <p>© 2026 LexSocial AI. Phát triển bởi <span className="font-bold">CMC-404-Not-Found</span>.</p>
            <p className="mt-1 opacity-75">Dữ liệu được trích xuất tự động, mang tính chất tham khảo. Luôn đối chiếu với Văn bản gốc.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
