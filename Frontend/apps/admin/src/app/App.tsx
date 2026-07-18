import { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
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
import { appBasename } from '../lib/base';
import DashboardPage from '../features/dashboard/Dashboard';
import AlertsPage from '../features/alerts/Alerts';
import QAAdminPage from '../features/qa/QAAdmin';
import IngestPage from '../features/ingest/Ingest';
import DiffPage from '../features/diff/DiffPage';
import GraphPage from '../features/graph/GraphPage';
import JobsPage from '../features/jobs/JobsPage';
import BriefsPage from '../features/briefs/BriefsPage';
import SuggestionsPage from '../features/suggestions/SuggestionsPage';
import SocialPage from '../features/social/SocialPage';
import ReviewPage from '../features/review/ReviewPage';
import KhoanPage from '../features/khoan/KhoanPage';
import LoginPage from '../features/auth/Login';

type NavItem = { to: string; label: string; icon: typeof SquaresFour };

const MAIN_NAV: NavItem[] = [
  { to: '/', label: 'Tổng quan', icon: SquaresFour },
  { to: '/alerts', label: 'Cảnh báo rủi ro', icon: Bell },
  { to: '/social', label: 'Radar MXH', icon: Broadcast },
  { to: '/qa', label: 'Hỏi đáp pháp lý', icon: ListMagnifyingGlass },
  { to: '/review', label: 'Hàng đợi duyệt', icon: ListChecks },
  { to: '/briefs', label: 'Bản tin', icon: Article },
  { to: '/suggestions', label: 'Đề xuất đính chính', icon: PenNib },
];

const DATA_NAV: NavItem[] = [
  { to: '/van-ban', label: 'Số hóa văn bản', icon: FileText },
  { to: '/jobs', label: 'Tiến trình Jobs', icon: HardDrives },
  { to: '/diff', label: 'So sánh Diff', icon: GitDiff },
  { to: '/graph', label: 'Đồ thị tri thức', icon: ShareNetwork },
];

function Sidebar({ onLogout }: { onLogout: () => void }) {
  const location = useLocation();
  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname === path || location.pathname.startsWith(`${path}/`);

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
      </div>
    </aside>
  );
}

function AppContent({ onLogout }: { onLogout: () => void }) {
  return (
    <div className="relative min-h-screen bg-background font-sans text-ink">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(37,87,214,0.06),_transparent_50%)]" />
      <Sidebar onLogout={onLogout} />
      <main className="admin-page-enter relative ml-[268px] min-h-screen p-6 sm:p-8 lg:p-10">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/social" element={<SocialPage />} />
          <Route path="/qa" element={<QAAdminPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/briefs" element={<BriefsPage />} />
          <Route path="/suggestions" element={<SuggestionsPage />} />
          <Route path="/van-ban" element={<IngestPage />} />
          <Route path="/khoan/:id" element={<KhoanPage />} />
          <Route path="/diff" element={<DiffPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/jobs" element={<JobsPage />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
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
    <Router basename={appBasename() === '/' ? undefined : appBasename()}>
      <AppContent onLogout={logout} />
    </Router>
  );
}

export default App;
