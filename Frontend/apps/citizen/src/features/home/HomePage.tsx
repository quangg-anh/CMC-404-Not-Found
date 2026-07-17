import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { MagnifyingGlass, BookOpen, Article, Scales, ArrowRight, Sparkle, Clock, ShieldCheck, LockKey, Gavel, KeyReturn, Spinner, FileText, PlayCircle } from '@phosphor-icons/react';
import { apiGet } from '../../lib/api';

interface HomeBrief {
  id: string;
  tieu_de: string;
  media_type: string;
  published_at?: string;
}

function Header() {
  return (
    <header className="fixed top-0 inset-x-0 bg-white/80 backdrop-blur-xl border-b border-slate-200/50 z-50 transition-all duration-300">
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
          <Link to="/login" className="px-6 py-2 rounded-full text-sm font-bold text-white bg-slate-900 hover:bg-slate-800 transition-all shadow-md hover:shadow-lg hover:-translate-y-0.5">
            Đăng nhập
          </Link>
        </nav>
      </div>
    </header>
  );
}

function HeroSection() {
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    navigate('/ask');
  };

  return (
    <div className="relative overflow-hidden bg-[#0a0f1c] min-h-screen flex items-center justify-center pt-20 selection:bg-brand selection:text-white">
      {/* Premium Dark Background Effects */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {/* Dynamic Glows */}
        <div className="absolute -top-[20%] left-[10%] w-[60%] h-[60%] rounded-full bg-brand/10 blur-[120px] mix-blend-screen animate-pulse" style={{ animationDuration: '4s' }} />
        <div className="absolute top-[20%] right-[5%] w-[40%] h-[40%] rounded-full bg-blue-600/10 blur-[100px] mix-blend-screen" />
        <div className="absolute bottom-[-10%] left-[40%] w-[50%] h-[50%] rounded-full bg-orange-500/5 blur-[120px] mix-blend-screen" />
        
        {/* Subtle grid pattern for a technical AI feel */}
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')] [mask-image:linear-gradient(to_bottom,white_10%,transparent_90%)]" />
      </div>

      <div className="max-w-5xl w-full mx-auto px-4 sm:px-6 relative z-10 text-center flex flex-col items-center">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-white/90 text-sm font-semibold mb-8 backdrop-blur-md shadow-2xl hover:bg-white/10 hover:border-white/20 transition-all cursor-default">
          <Sparkle size={16} weight="fill" className="text-brand" />
          <span className="tracking-wide">Phiên bản thử nghiệm AI 2026</span>
        </div>
        
        <h2 className="text-5xl sm:text-7xl lg:text-[80px] font-black text-white tracking-tight mb-8 leading-[1.05] drop-shadow-2xl">
          Tra cứu pháp luật <br className="hidden sm:block" />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-red-400 via-brand to-orange-400">
            nhanh chóng & chính xác
          </span>
        </h2>
        
        <p className="text-lg sm:text-xl text-slate-300 mb-12 max-w-2xl mx-auto leading-relaxed font-medium">
          Hệ thống Trợ lý Ảo AI giải đáp thắc mắc dựa trên cơ sở dữ liệu chính thức, luôn đính kèm <strong className="text-white border-b border-brand/50 pb-0.5">Căn cứ pháp lý nguyên văn</strong>.
        </p>
        
        <form onSubmit={handleSearch} className="relative w-full max-w-3xl mx-auto group">
          {/* Neon Glow under the input */}
          <div className="absolute -inset-1 bg-gradient-to-r from-brand/30 via-red-500/20 to-orange-500/30 rounded-[32px] blur-xl group-focus-within:blur-2xl transition-all duration-500 opacity-50 group-hover:opacity-100"></div>
          
          <div className="relative flex items-center bg-[#151e32]/80 backdrop-blur-2xl border border-white/10 rounded-[28px] p-2 shadow-2xl transition-all group-focus-within:bg-[#1e293b]/90 group-focus-within:border-brand/50 group-focus-within:shadow-brand/20 ring-4 ring-transparent group-focus-within:ring-brand/10">
            <div className="pl-5 pr-3 flex items-center pointer-events-none">
              <MagnifyingGlass size={26} className="text-slate-400 group-focus-within:text-brandLight transition-colors" />
            </div>
            
            <input 
              type="text" 
              placeholder="Ví dụ: Quy định thai sản cho lao động nam 2026?"
              className="flex-1 bg-transparent border-none text-white placeholder:text-slate-500 text-lg sm:text-xl font-medium focus:outline-none py-5 px-2 w-full"
              autoComplete="off"
            />
            
            {/* Enter Hint */}
            <div className="hidden sm:flex items-center px-4 mr-2 text-slate-400 border border-slate-700/50 rounded-xl bg-slate-800/50 h-10 gap-1 font-mono text-xs font-bold pointer-events-none shadow-inner">
              <KeyReturn size={14} weight="bold" /> ENTER
            </div>

            <button 
              type="submit"
              className="bg-gradient-to-r from-brand to-red-700 hover:from-red-600 hover:to-brand text-white font-bold py-4 px-8 rounded-2xl transition-all duration-300 shadow-lg hover:shadow-brand/40 flex items-center gap-2 hover:scale-[1.02] active:scale-95 shrink-0"
            >
              <span className="hidden sm:inline text-lg">Hỏi AI</span>
              <ArrowRight size={20} weight="bold" />
            </button>
          </div>
        </form>

        <div className="mt-16 flex flex-wrap items-center justify-center gap-x-12 gap-y-6 text-sm text-slate-400 font-semibold tracking-wide">
          <span className="flex items-center gap-2 hover:text-slate-200 transition-colors cursor-default"><ShieldCheck size={22} className="text-emerald-400" /> Nguồn dữ liệu chính thống</span>
          <span className="flex items-center gap-2 hover:text-slate-200 transition-colors cursor-default"><Clock size={22} className="text-sky-400" /> Cập nhật thời gian thực</span>
          <span className="flex items-center gap-2 hover:text-slate-200 transition-colors cursor-default"><LockKey size={22} className="text-purple-400" /> Bảo mật & Riêng tư</span>
        </div>
      </div>
    </div>
  );
}

function briefIcon(mt: string) {
  if (mt === 'video') return <PlayCircle size={24} className="text-blue-600" weight="fill" />;
  if (mt === 'image') return <Gavel size={24} className="text-brand" />;
  return <FileText size={24} className="text-emerald-600" weight="fill" />;
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
    <div className="relative bg-slate-50">
      {/* Subtle top border integration */}
      <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-slate-200 to-transparent"></div>
      
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-32 relative z-20">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-16 px-2 gap-6">
          <div className="max-w-2xl">
            <h3 className="text-4xl sm:text-5xl font-black text-slate-900 tracking-tight">
              Điểm tin Pháp luật
            </h3>
            <p className="text-slate-500 font-medium mt-4 text-xl">Các văn bản và chính sách mới nhất vừa được ban hành, được tóm tắt siêu tốc bởi AI.</p>
          </div>
          <Link to="/news" className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-white border border-slate-200 shadow-sm hover:border-slate-300 hover:shadow-md text-slate-800 font-bold rounded-full transition-all group">
            Xem tất cả tin tức <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
          </Link>
        </div>

        {loading ? (
          <div className="py-16 text-center text-slate-400 font-semibold flex items-center justify-center gap-2">
            <Spinner size={20} className="animate-spin" /> Đang tải tin tức…
          </div>
        ) : news.length === 0 ? (
          <div className="py-16 text-center text-slate-400 font-medium bg-white rounded-[32px] border border-slate-100">
            Chưa có bài tóm tắt nào được xuất bản.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {news.map((item) => (
              <Link to={`/news/${item.id}`} key={item.id} className="group relative bg-white rounded-[32px] p-2 shadow-sm hover:shadow-2xl hover:shadow-slate-200/50 border border-slate-100 transition-all duration-500 hover:-translate-y-2 cursor-pointer">
                <div className="absolute inset-0 bg-gradient-to-br from-brand/5 to-transparent opacity-0 group-hover:opacity-100 rounded-[32px] transition-opacity duration-500"></div>
                <div className="relative h-full bg-white rounded-[24px] p-8 flex flex-col justify-between border border-transparent group-hover:border-slate-100 transition-colors z-10">

                  <div>
                    <div className="flex items-center justify-between mb-8">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-full bg-slate-50 flex items-center justify-center border border-slate-100 group-hover:scale-110 group-hover:bg-white transition-all duration-300 shadow-sm">
                          {briefIcon(item.media_type)}
                        </div>
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-widest">
                          {item.media_type === 'video' ? 'Video' : item.media_type === 'image' ? 'Infographic' : 'Bài viết'}
                        </span>
                      </div>
                    </div>
                    <h4 className="text-2xl font-bold text-slate-800 leading-[1.4] group-hover:text-brand transition-colors duration-300 line-clamp-4">
                      {item.tieu_de}
                    </h4>
                  </div>

                  <div className="mt-10 pt-6 border-t border-slate-100 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-bold text-slate-500 flex items-center gap-1.5 bg-slate-50 px-3 py-1.5 rounded-lg">
                        <Clock size={14} weight="bold" /> {item.published_at ? item.published_at.slice(0, 10) : 'Mới xuất bản'}
                      </span>
                    </div>
                    <div className="flex items-center text-sm font-bold text-brand opacity-0 -translate-x-4 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300">
                      Đọc tóm tắt <ArrowRight size={16} weight="bold" className="ml-1" />
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans selection:bg-brand selection:text-white">
      <Header />
      <main className="flex-1">
        <HeroSection />
        <NewsHighlight />
      </main>
      <footer className="bg-white border-t border-slate-200 pt-16 pb-8 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-12 mb-16">
            <div className="md:col-span-2 flex flex-col items-start">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 bg-brand rounded-lg flex items-center justify-center text-white shadow-sm">
                  <Scales size={24} weight="fill" />
                </div>
                <span className="text-2xl font-black text-slate-900 tracking-tight">LexSocial<span className="text-brand">AI</span></span>
              </div>
              <p className="text-slate-500 font-medium leading-relaxed max-w-sm mb-6">
                Nền tảng Tra cứu Pháp luật thông minh dành cho công dân. Dữ liệu được thu thập và phân tích bởi AI đảm bảo tính chính xác và kịp thời.
              </p>
            </div>
            
            <div>
              <h4 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-6">Sản phẩm</h4>
              <ul className="space-y-4 text-slate-500 font-medium">
                <li><Link to="/" className="hover:text-brand transition-colors">Trợ lý Pháp lý AI</Link></li>
                <li><Link to="/van-ban" className="hover:text-brand transition-colors">Tra cứu Văn bản</Link></li>
                <li><Link to="/news" className="hover:text-brand transition-colors">Tin tức Tóm tắt</Link></li>
              </ul>
            </div>
            
            <div>
              <h4 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-6">Tổ chức</h4>
              <ul className="space-y-4 text-slate-500 font-medium">
                <li><a href="#" className="hover:text-brand transition-colors">Về chúng tôi</a></li>
                <li><a href="#" className="hover:text-brand transition-colors">Điều khoản sử dụng</a></li>
                <li><a href="#" className="hover:text-brand transition-colors">Chính sách bảo mật</a></li>
              </ul>
            </div>
          </div>
          
          <div className="pt-8 border-t border-slate-200 flex flex-col md:flex-row items-center justify-between gap-4">
            <p className="text-slate-500 text-sm font-semibold">
              © 2026 LexSocial AI. Phát triển bởi <span className="text-slate-900">CMC-404-Not-Found</span>.
            </p>
            <p className="text-slate-400 text-sm font-medium">
              Cập nhật lần cuối: Tháng 7, 2026
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
