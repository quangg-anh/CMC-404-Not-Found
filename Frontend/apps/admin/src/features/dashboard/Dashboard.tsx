import { useEffect, useState } from 'react';
import { WarningCircle, ShareNetwork, Article, ListMagnifyingGlass, ArrowUpRight, Spinner } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { apiGet } from '../../lib/api';

interface DashboardSummary {
  alerts: { high_severity_active: number; total_monitored: number };
  pipeline_jobs: { running: number; failed: number; needs_review: number; health_status: string };
  knowledge_graph: { legal_documents_count: number; social_posts_monitored: number; sync_status: string };
  content_briefs: { pending_review: number; ready_suggestions: number };
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    apiGet<DashboardSummary>('/admin/dashboard/summary')
      .then((data) => alive && setSummary(data))
      .catch((err) => alive && setError(err instanceof Error ? err.message : 'Lỗi tải dữ liệu'))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const fmt = (n: number | undefined) => (n ?? 0).toLocaleString('vi-VN');

  return (
    <div className="space-y-6 max-w-6xl">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-5 py-4 text-sm font-semibold">
          Không thể tải số liệu tổng quan: {error}
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-surface rounded-2xl p-6 shadow-soft">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-muted text-sm font-bold mb-1">Văn bản trong đồ thị</p>
              <h3 className="text-3xl font-bold text-primary">{loading ? '—' : fmt(summary?.knowledge_graph.legal_documents_count)}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-gradient-accent text-white flex items-center justify-center shadow-md">
              <Article size={24} weight="fill" />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-sm">
            <span className="text-success font-bold flex items-center">{summary?.knowledge_graph.sync_status === 'in_sync' ? 'Đồng bộ' : summary?.knowledge_graph.sync_status ?? '—'}</span>
            <span className="text-muted font-medium">Neo4j</span>
          </div>
        </div>

        <div className="bg-surface rounded-2xl p-6 shadow-soft relative overflow-hidden">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-muted text-sm font-bold mb-1">Cảnh báo giám sát</p>
              <h3 className="text-3xl font-bold text-primary">{loading ? '—' : fmt(summary?.alerts.total_monitored)}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-gradient-danger text-white flex items-center justify-center shadow-md">
              <WarningCircle size={24} weight="fill" />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-sm">
            <span className="text-destructive font-bold">{fmt(summary?.alerts.high_severity_active)} nghiêm trọng</span>
            <span className="text-muted font-medium">đang hoạt động</span>
          </div>
        </div>

        <div className="bg-surface rounded-2xl p-6 shadow-soft">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-muted text-sm font-bold mb-1">Bài MXH giám sát</p>
              <h3 className="text-3xl font-bold text-primary">{loading ? '—' : fmt(summary?.knowledge_graph.social_posts_monitored)}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-gradient-success text-white flex items-center justify-center shadow-md">
              <ShareNetwork size={24} weight="fill" />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-sm">
            <span className="text-success font-bold flex items-center"><ArrowUpRight size={14} className="mr-0.5" />{fmt(summary?.content_briefs.pending_review)}</span>
            <span className="text-muted font-medium">bài chờ duyệt</span>
          </div>
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-muted text-sm font-semibold">
          <Spinner size={16} className="animate-spin" /> Đang tải số liệu thời gian thực…
        </div>
      )}

      {/* Quick Actions */}
      <section className="bg-surface rounded-2xl p-6 shadow-soft mt-6">
        <h3 className="text-base font-bold text-primary mb-6">Thao tác nhanh</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <Link to="/alerts" className="flex flex-col items-center justify-center p-6 bg-background rounded-2xl hover:shadow-card transition-shadow border border-transparent hover:border-border group">
            <div className="w-14 h-14 bg-surface rounded-xl flex items-center justify-center shadow-soft mb-4 group-hover:-translate-y-1 transition-transform">
              <WarningCircle size={28} className="text-destructive" weight="fill" />
            </div>
            <span className="text-sm font-bold text-primary">Xử lý cảnh báo</span>
          </Link>
          <Link to="/van-ban" className="flex flex-col items-center justify-center p-6 bg-background rounded-2xl hover:shadow-card transition-shadow border border-transparent hover:border-border group">
            <div className="w-14 h-14 bg-surface rounded-xl flex items-center justify-center shadow-soft mb-4 group-hover:-translate-y-1 transition-transform">
              <Article size={28} className="text-secondaryAccent" weight="fill" />
            </div>
            <span className="text-sm font-bold text-primary">Số hóa văn bản</span>
          </Link>
          <Link to="/diff" className="flex flex-col items-center justify-center p-6 bg-background rounded-2xl hover:shadow-card transition-shadow border border-transparent hover:border-border group">
            <div className="w-14 h-14 bg-surface rounded-xl flex items-center justify-center shadow-soft mb-4 group-hover:-translate-y-1 transition-transform">
              <ShareNetwork size={28} className="text-accent" weight="fill" />
            </div>
            <span className="text-sm font-bold text-primary">So sánh văn bản</span>
          </Link>
          <Link to="/qa" className="flex flex-col items-center justify-center p-6 bg-background rounded-2xl hover:shadow-card transition-shadow border border-transparent hover:border-border group">
            <div className="w-14 h-14 bg-surface rounded-xl flex items-center justify-center shadow-soft mb-4 group-hover:-translate-y-1 transition-transform">
              <ListMagnifyingGlass size={28} className="text-success" weight="fill" />
            </div>
            <span className="text-sm font-bold text-primary">QA Bot Nội bộ</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
