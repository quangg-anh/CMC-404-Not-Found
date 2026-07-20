import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import {
  ShieldCheck,
  SquaresFour,
  Bell,
  ListMagnifyingGlass,
  FileText,
  ShareNetwork,
  HardDrives,
  Article,
  ListChecks,
  Broadcast,
  PenNib,
  Scales,
  SignOut,
  GitDiff,
} from '@phosphor-icons/react';
import { apiGet, clearToken, getToken } from '../lib/api';
import DashboardPage from '../admin/features/dashboard/Dashboard';
import AlertsPage from '../admin/features/alerts/Alerts';
import QAAdminPage from '../admin/features/qa/QAAdmin';
import IngestPage from '../admin/features/ingest/Ingest';
import DiffPage from '../admin/features/diff/DiffPage';
import GraphPage from '../admin/features/graph/GraphPage';
import JobsPage from '../admin/features/jobs/JobsPage';
import BriefsPage from '../admin/features/briefs/BriefsPage';
import SuggestionsPage from '../admin/features/suggestions/SuggestionsPage';
import SocialPage from '../admin/features/social/SocialPage';
import ReviewPage from '../admin/features/review/ReviewPage';
import KhoanPage from '../admin/features/khoan/KhoanPage';
import LoginPage from '../admin/features/auth/Login';
import HomePage from '../citizen/features/home/HomePage';
import AskPage from '../citizen/features/ask/AskPage';
import VanBanPage from '../citizen/features/van-ban/VanBanPage';
import NewsPage from '../citizen/features/news/NewsPage';
import NewsDetailPage from '../citizen/features/news/NewsDetailPage';
import { CitizenChatBubble } from '../citizen/components/CitizenChatBubble';

type NavItem = { to: string; label: string; icon: typeof SquaresFour };

const MAIN_NAV: NavItem[] = [
  { to: '/admin', label: 'Tổng quan', icon: SquaresFour },
  { to: '/admin/alerts', label: 'Cảnh báo rủi ro', icon: Bell },
  { to: '/admin/social', label: 'Radar thông tin', icon: Broadcast },
  { to: '/admin/qa', label: 'Hỏi đáp pháp lý', icon: ListMagnifyingGlass },
  { to: '/admin/review', label: 'Hàng đợi duyệt', icon: ListChecks },
  { to: '/admin/briefs', label: 'Bản tin', icon: Article },
  { to: '/admin/suggestions', label: 'Đề xuất đính chính', icon: PenNib },
];

const DATA_NAV: NavItem[] = [
  { to: '/admin/van-ban', label: 'Số hóa văn bản', icon: FileText },
  { to: '/admin/jobs', label: 'Tiến trình Jobs', icon: HardDrives },
  { to: '/admin/diff', label: 'So sánh Diff', icon: GitDiff },
  { to: '/admin/graph', label: 'Đồ thị tri thức', icon: ShareNetwork },
];

function Sidebar({ onLogout }: { onLogout: () => void }) {
  const location = useLocation();
  const isActive = (path: string) =>
    path === '/admin'
      ? location.pathname === '/admin' || location.pathname === '/admin/'
      : location.pathname === path || location.pathname.startsWith(`${path}/`);

  const linkClass = (path: string) =>
    `group flex items-center gap-3 rounded-control px-3 py-2.5 text-sm font-semibold transition-all duration-200 ${
      isActive(path)
        ? 'bg-primary text-white shadow-[0_8px_18px_-10px_rgba(37,87,214,0.7)]'
        : 'text-muted hover:bg-primary-soft/80 hover:text-primary'
    }`;

  const renderNav = (items: NavItem[]) =>
    items.map(({ to, label, icon: IconCmp }) => (
      <Link key={to} to={to} className={linkClass(to)} aria-current={isActive(to) ? 'page' : undefined}>
        <IconCmp size={18} weight={isActive(to) ? 'fill' : 'bold'} aria-hidden />
        {label}
      </Link>
    ));

  return (
    <aside className="fixed left-0 top-0 z-50 flex h-screen w-[268px] flex-col border-r border-border bg-surface/95 shadow-soft backdrop-blur-md">
      <div className="flex items-center gap-3 border-b border-border/80 px-5 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-[12px] bg-gradient-to-br from-primary to-[#4F7FE8] text-white shadow-sm">
          <Scales size={22} weight="fill" aria-hidden />
        </div>
        <div>
          <p className="font-display text-base font-extrabold leading-none tracking-tight">
            <span className="admin-brand-gradient">LexSocial AI</span>
          </p>
          <p className="mt-1 text-xs font-medium text-muted">Cổng quản trị</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Điều hướng admin">
        {renderNav(MAIN_NAV)}
        <p className="px-3 pb-1 pt-5 text-[11px] font-bold uppercase tracking-wider text-muted">Dữ liệu</p>
        {renderNav(DATA_NAV)}
      </nav>

      <div className="border-t border-border/80 p-3">
        <button type="button" onClick={onLogout} className="admin-btn-secondary w-full justify-start !text-muted">
          <SignOut size={18} weight="bold" aria-hidden />
          Đăng xuất
        </button>
        <p className="mt-2 flex items-center gap-1.5 px-1 text-[11px] font-medium text-muted">
          <ShieldCheck size={12} weight="fill" className="text-success" aria-hidden />
          Phiên cán bộ · có kiểm duyệt
        </p>
        <Link to="/" className="mt-2 block px-1 text-[11px] font-semibold text-primary hover:underline">
          ← Cổng người dân
        </Link>
      </div>
    </aside>
  );
}

function AdminShell() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => Boolean(getToken()));

  useEffect(() => {
    if (!isAuthenticated) return;
    apiGet<{ is_admin?: boolean }>('/auth/me')
      .then((me) => {
        if (!me?.is_admin) {
          clearToken();
          setIsAuthenticated(false);
        }
      })
      .catch(() => {
        /* keep session on transient errors */
      });
  }, [isAuthenticated]);

  const logout = () => {
    clearToken();
    setIsAuthenticated(false);
  };

  if (!isAuthenticated) {
    return <LoginPage onLogin={() => setIsAuthenticated(true)} />;
  }

  return (
    <div className="relative min-h-screen bg-background font-sans text-ink">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(37,87,214,0.06),_transparent_50%)]" />
      <Sidebar onLogout={logout} />
      <main className="admin-page-enter relative ml-[268px] min-h-screen p-6 sm:p-8 lg:p-10">
        <Routes>
          <Route index element={<DashboardPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="social" element={<SocialPage />} />
          <Route path="qa" element={<QAAdminPage />} />
          <Route path="review" element={<ReviewPage />} />
          <Route path="briefs" element={<BriefsPage />} />
          <Route path="suggestions" element={<SuggestionsPage />} />
          <Route path="van-ban" element={<IngestPage />} />
          <Route path="khoan/:id" element={<KhoanPage />} />
          <Route path="diff" element={<DiffPage />} />
          <Route path="graph" element={<GraphPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function CitizenScrollTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function CitizenRoutes() {
  return (
    <div className="relative flex min-h-[100dvh] flex-col">
      <CitizenScrollTop />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/ask" element={<AskPage />} />
        <Route path="/van-ban" element={<VanBanPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/news/:id" element={<NewsDetailPage />} />
      </Routes>
      <CitizenChatBubble />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/admin/*" element={<AdminShell />} />
        <Route path="/*" element={<CitizenRoutes />} />
      </Routes>
    </BrowserRouter>
  );
}
