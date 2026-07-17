// Force HMR reload
import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { ShieldCheck, SquaresFour, Bell, ListMagnifyingGlass, FileText, ShareNetwork, HardDrives, Article, ListChecks } from '@phosphor-icons/react';
import DashboardPage from '../features/dashboard/Dashboard';
import AlertsPage from '../features/alerts/Alerts';
import QAAdminPage from '../features/qa/QAAdmin';
import IngestPage from '../features/ingest/Ingest';
import DiffPage from '../features/diff/DiffPage';
import GraphPage from '../features/graph/GraphPage';
import JobsPage from '../features/jobs/JobsPage';
import BriefsPage from '../features/briefs/BriefsPage';
import ReviewPage from '../features/review/ReviewPage';
import KhoanPage from '../features/khoan/KhoanPage';
import LoginPage from '../features/auth/Login';

function Sidebar() {
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path;

  const navItemClass = (path: string) => `
    flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all font-semibold text-sm mb-1
    ${isActive(path) 
      ? 'bg-primary/5 text-primary' 
      : 'text-muted hover:bg-surface hover:text-primary'}
  `;

  const iconWrapperClass = (path: string) => `
    w-8 h-8 rounded-md flex items-center justify-center transition-colors
    ${isActive(path) ? 'bg-primary text-white shadow-sm' : 'bg-transparent text-muted'}
  `;

  return (
    <aside className="w-[260px] h-screen bg-surface border-r border-border fixed left-0 top-0 flex flex-col z-50 shadow-sm">
      <div className="p-6 flex items-center gap-3 border-b border-border/50">
        <div className="w-8 h-8 bg-primary rounded-md flex items-center justify-center text-white shadow-sm">
          <ShieldCheck size={20} weight="fill" />
        </div>
        <span className="text-primary font-bold tracking-tight">LexSocial AI</span>
      </div>

      <div className="flex-1 px-4 overflow-y-auto py-6 space-y-0.5">
        <Link to="/" className={navItemClass('/')}>
          <div className={iconWrapperClass('/')}><SquaresFour size={16} weight="fill" /></div>
          Tổng quan
        </Link>
        <Link to="/alerts" className={navItemClass('/alerts')}>
          <div className={iconWrapperClass('/alerts')}><Bell size={16} weight="fill" /></div>
          Cảnh báo rủi ro
        </Link>
        <Link to="/qa" className={navItemClass('/qa')}>
          <div className={iconWrapperClass('/qa')}><ListMagnifyingGlass size={16} weight="fill" /></div>
          Hỏi đáp Pháp lý
        </Link>
        <Link to="/review" className={navItemClass('/review')}>
          <div className={iconWrapperClass('/review')}><ListChecks size={16} weight="fill" /></div>
          Hàng đợi duyệt
        </Link>
        <Link to="/briefs" className={navItemClass('/briefs')}>
          <div className={iconWrapperClass('/briefs')}><Article size={16} weight="fill" /></div>
          Bản tin & Đề xuất
        </Link>
        
        <div className="pt-6 pb-2">
          <p className="px-4 text-xs font-bold text-muted uppercase tracking-wider">Quản trị Dữ liệu</p>
        </div>
        <Link to="/van-ban" className={navItemClass('/van-ban')}>
          <div className={iconWrapperClass('/van-ban')}><FileText size={16} weight="fill" /></div>
          Số hóa văn bản (Ingest)
        </Link>
        <Link to="/jobs" className={navItemClass('/jobs')}>
          <div className={iconWrapperClass('/jobs')}><HardDrives size={16} weight="fill" /></div>
          Tiến trình (Jobs)
        </Link>
        <Link to="/diff" className={navItemClass('/diff')}>
          <div className={iconWrapperClass('/diff')}><ListMagnifyingGlass size={16} weight="fill" /></div>
          So sánh (Diff)
        </Link>
        <Link to="/graph" className={navItemClass('/graph')}>
          <div className={iconWrapperClass('/graph')}><ShareNetwork size={16} weight="fill" /></div>
          Đồ thị Tri thức
        </Link>
      </div>
    </aside>
  );
}

function AppContent() {
  return (
    <div className="min-h-screen bg-[#f8fafc] font-sans text-slate-900 relative">
      <Sidebar />
      <main className="ml-[260px] p-10 min-h-screen">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/qa" element={<QAAdminPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/briefs" element={<BriefsPage />} />
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
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  if (!isAuthenticated) {
    return <LoginPage onLogin={() => setIsAuthenticated(true)} />;
  }

  return (
    <Router basename="/admin">
      <AppContent />
    </Router>
  );
}

export default App;
