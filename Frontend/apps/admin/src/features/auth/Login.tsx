import { useState } from 'react';
import { ShieldCheck, Eye, EyeSlash, ArrowRight, Spinner, Scales, WarningCircle } from '@phosphor-icons/react';
import { apiPost, setToken } from '../../lib/api';

interface LoginResponse {
  token: string;
  user: { id: string; email: string; full_name: string | null; role: string; roles: string[]; is_admin: boolean };
}

export default function LoginPage({ onLogin }: { onLogin: (role: string) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      // Real authentication against the Postgres `users` table (bcrypt via pgcrypto).
      const res = await apiPost<LoginResponse>('/auth/login', { email: email.trim(), password });
      setToken(res.token);
      if (res.user.is_admin) {
        onLogin(res.user.role);
      } else {
        // Citizen accounts don't belong in the admin console — send them to the citizen portal.
        window.location.href = '/citizen';
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Đăng nhập thất bại. Vui lòng thử lại.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex bg-surface">
      {/* Cột trái: Branding (Ẩn trên mobile) */}
      <div className="hidden lg:flex w-5/12 bg-slate-900 flex-col justify-between p-12 relative overflow-hidden">
        {/* Abstract Pattern background */}
        <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(#ffffff 1px, transparent 1px)', backgroundSize: '32px 32px' }}></div>
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-accent rounded-full mix-blend-multiply filter blur-[128px] opacity-40"></div>
        <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-secondaryAccent rounded-full mix-blend-multiply filter blur-[128px] opacity-40"></div>
        
        <div className="relative z-10 flex items-center gap-3 animate-fade-in-up">
          <div className="w-12 h-12 bg-white/10 rounded-xl flex items-center justify-center backdrop-blur-md border border-white/20">
            <Scales size={28} className="text-white" weight="fill" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">LexSocial AI</h1>
        </div>

        <div className="relative z-10 max-w-md animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <div className="inline-block px-4 py-1.5 rounded-full bg-white/10 border border-white/20 text-white text-xs font-bold tracking-wider uppercase mb-6 backdrop-blur-md">
            Hệ thống Quản trị
          </div>
          <h2 className="text-4xl font-bold text-white leading-tight mb-6">
            Kiểm soát dư luận.<br />
            Minh bạch pháp lý.
          </h2>
          <p className="text-slate-400 text-lg leading-relaxed mb-10">
            Trung tâm chỉ huy số hóa hệ thống văn bản quy phạm pháp luật và phân tích thông tin mạng xã hội bằng Trí tuệ Nhân tạo.
          </p>
          <div className="flex items-center gap-6 text-sm font-medium text-slate-300">
            <div className="flex items-center gap-2">
              <ShieldCheck size={20} className="text-success" weight="fill" />
              Kiểm duyệt bởi con người trước khi xuất bản
            </div>
          </div>
        </div>

        <div className="relative z-10 animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
          <p className="text-slate-500 text-sm">© 2026 LexSocial AI.</p>
        </div>
      </div>

      {/* Cột phải: Form Đăng nhập */}
      <div className="w-full lg:w-7/12 flex flex-col justify-center px-8 sm:px-24 xl:px-32 relative bg-background/50">
        <div className="w-full max-w-md mx-auto animate-fade-in-up">
          
          <div className="mb-10 text-center lg:text-left">
            <div className="lg:hidden w-16 h-16 bg-slate-900 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg">
              <Scales size={32} className="text-white" weight="fill" />
            </div>
            <h2 className="text-3xl font-bold text-primary tracking-tight mb-2">Đăng nhập cổng quản trị</h2>
            <p className="text-muted text-base">Vui lòng sử dụng tài khoản định danh cán bộ</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label className="text-sm font-bold text-primary">Mã định danh / Email</label>
              <input 
                type="text" 
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="VD: admin@local (cán bộ) hoặc citizen@local (người dân)"
                className="w-full px-5 py-4 bg-surface border border-border rounded-xl text-primary font-medium focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm"
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-sm font-bold text-primary">Mật khẩu xác thực</label>
              </div>
              <div className="relative">
                <input 
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-5 py-4 bg-surface border border-border rounded-xl text-primary font-medium focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm pr-12"
                />
                <button 
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors"
                >
                  {showPassword ? <EyeSlash size={22} /> : <Eye size={22} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <div className="flex items-center gap-2">
                <input type="checkbox" id="remember" className="w-4 h-4 rounded border-border text-primary focus:ring-primary cursor-pointer" />
                <label htmlFor="remember" className="text-sm font-medium text-muted cursor-pointer">Lưu phiên đăng nhập</label>
              </div>
              <a href="#" className="text-sm font-bold text-primary hover:text-accent transition-colors">Quên mật khẩu?</a>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-semibold">
                <WarningCircle size={18} weight="fill" className="shrink-0" /> {error}
              </div>
            )}

            <button 
              type="submit" 
              disabled={isLoading || !email || !password}
              className="w-full bg-slate-900 text-white py-4 rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-slate-800 hover:shadow-lg hover:-translate-y-0.5 transition-all disabled:opacity-70 disabled:hover:translate-y-0 disabled:cursor-not-allowed mt-4 group"
            >
              {isLoading ? (
                <>
                  <Spinner size={20} className="animate-spin" /> Đang kiểm tra mã...
                </>
              ) : (
                <>
                  Đăng nhập hệ thống
                  <ArrowRight size={20} weight="bold" className="group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </button>
          </form>

          <div className="mt-12 pt-8 border-t border-border flex flex-col items-center gap-3 text-sm">
            <p className="text-muted flex items-center gap-2">
              <ShieldCheck size={18} weight="fill" className="text-slate-400" />
              Xác thực bằng tài khoản định danh cán bộ
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
