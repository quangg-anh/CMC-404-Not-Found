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
      const res = await apiPost<LoginResponse>('/auth/login', { email: email.trim(), password });
      setToken(res.token);
      if (res.user.is_admin) {
        onLogin(res.user.role);
      } else {
        window.location.href = '/citizen';
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Đăng nhập thất bại. Vui lòng thử lại.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full bg-surface">
      <div className="relative hidden w-5/12 flex-col justify-between overflow-hidden bg-gradient-to-br from-[#0F172A] via-[#1E3A8A] to-primary p-12 lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-20"
          style={{
            backgroundImage: 'radial-gradient(#ffffff 1px, transparent 1px)',
            backgroundSize: '28px 28px',
          }}
        />
        <div className="pointer-events-none absolute -left-24 -top-24 h-80 w-80 rounded-full bg-accent/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 -right-16 h-96 w-96 rounded-full bg-primary/40 blur-3xl" />

        <div className="relative z-10 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-[14px] border border-white/20 bg-white/10 text-white backdrop-blur-md">
            <Scales size={28} weight="fill" aria-hidden />
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white">LexSocial AI</h1>
        </div>

        <div className="relative z-10 max-w-md">
          <p className="mb-5 inline-flex rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-white backdrop-blur-md">
            Hệ thống quản trị
          </p>
          <h2 className="mb-4 text-4xl font-extrabold leading-tight text-white">
            Kiểm soát dư luận.
            <br />
            Minh bạch pháp lý.
          </h2>
          <p className="mb-8 text-lg leading-relaxed text-white/70">
            Trung tâm chỉ huy số hóa văn bản QPPL và giám sát thông tin mạng xã hội kèm căn cứ pháp lý.
          </p>
          <p className="flex items-center gap-2 text-sm font-semibold text-white/85">
            <ShieldCheck size={20} className="text-emerald-300" weight="fill" aria-hidden />
            Kiểm duyệt bởi con người trước khi xuất bản
          </p>
        </div>

        <p className="relative z-10 text-sm text-white/45">© 2026 LexSocial AI</p>
      </div>

      <div className="relative flex w-full flex-col justify-center bg-background px-8 sm:px-16 lg:w-7/12 xl:px-28">
        <div className="mx-auto w-full max-w-md">
          <div className="mb-10 text-center lg:text-left">
            <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#4F7FE8] text-white shadow-lg lg:hidden">
              <Scales size={28} weight="fill" aria-hidden />
            </div>
            <h2 className="font-display text-3xl font-extrabold tracking-tight text-ink">Đăng nhập cổng quản trị</h2>
            <p className="mt-2 text-base text-muted">Dùng tài khoản định danh cán bộ</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <label className="text-sm font-bold text-ink" htmlFor="admin-email">
                Email
              </label>
              <input
                id="admin-email"
                type="text"
                name="username"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="VD: admin@local"
                className="admin-input"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-bold text-ink" htmlFor="admin-password">
                Mật khẩu
              </label>
              <div className="relative">
                <input
                  id="admin-password"
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="admin-input pr-12"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-primary"
                  aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                >
                  {showPassword ? <EyeSlash size={22} /> : <Eye size={22} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 rounded-control border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
                <WarningCircle size={18} weight="fill" className="shrink-0" aria-hidden />
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading || !email || !password}
              className="admin-btn-primary mt-2 w-full !min-h-[52px] !text-base"
            >
              {isLoading ? (
                <>
                  <Spinner size={20} className="animate-spin" aria-hidden /> Đang xác thực…
                </>
              ) : (
                <>
                  Đăng nhập
                  <ArrowRight size={20} weight="bold" aria-hidden />
                </>
              )}
            </button>
          </form>

          <p className="mt-10 flex items-center justify-center gap-2 border-t border-border pt-6 text-sm text-muted">
            <ShieldCheck size={18} weight="fill" className="text-primary" aria-hidden />
            Xác thực bằng tài khoản định danh cán bộ
          </p>
        </div>
      </div>
    </div>
  );
}
