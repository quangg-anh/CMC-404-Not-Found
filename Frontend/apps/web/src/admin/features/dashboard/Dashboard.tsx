import { useEffect, useState } from 'react';
import {
  WarningCircle,
  ShareNetwork,
  Article,
  ListMagnifyingGlass,
  Spinner,
  HardDrives,
  Bell,
  Broadcast,
  ArrowRight,
} from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { apiGet } from '../../../lib/api';
import { ErrorBanner, PageHeader, StatCard } from '../../components/AdminChrome';

interface DashboardSummary {
  alerts: { high_severity_active: number; total_monitored: number };
  pipeline_jobs: { running: number; failed: number; needs_review: number; health_status: string };
  knowledge_graph: {
    legal_documents_count: number;
    social_posts_monitored: number;
    topic_count?: number;
    sync_status: string;
  };
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
  const syncLabel =
    summary?.knowledge_graph.sync_status === 'in_sync'
      ? 'Neo4j đồng bộ'
      : summary?.knowledge_graph.sync_status === 'degraded'
        ? 'Neo4j lỗi / chậm'
        : 'Chưa kết nối Neo4j';

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Tổng quan vận hành"
        subtitle="Số liệu thời gian thực từ Postgres và Neo4j — không dùng dữ liệu giả."
        actions={
          loading ? (
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-muted">
              <Spinner size={16} className="animate-spin" aria-hidden /> Đang tải…
            </span>
          ) : null
        }
      />

      {error ? <ErrorBanner message={`Không thể tải số liệu tổng quan: ${error}`} /> : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Văn bản trong đồ thị"
          value={fmt(summary?.knowledge_graph.legal_documents_count)}
          hint={syncLabel}
          icon={Article}
          tone="primary"
          loading={loading}
        />
        <StatCard
          label="Cảnh báo đang mở"
          value={fmt(summary?.alerts.total_monitored)}
          hint={`${fmt(summary?.alerts.high_severity_active)} mức cao`}
          icon={Bell}
          tone="danger"
          loading={loading}
        />
        <StatCard
          label="Bài MXH giám sát"
          value={fmt(summary?.knowledge_graph.social_posts_monitored)}
          hint={`${fmt(summary?.knowledge_graph.topic_count)} chủ đề`}
          icon={Broadcast}
          tone="accent"
          loading={loading}
        />
        <StatCard
          label="Jobs đang chạy"
          value={fmt(summary?.pipeline_jobs.running)}
          hint={
            summary?.pipeline_jobs.health_status === 'healthy'
              ? `${fmt(summary?.pipeline_jobs.needs_review)} cần review`
              : `${fmt(summary?.pipeline_jobs.failed)} thất bại`
          }
          icon={HardDrives}
          tone={summary?.pipeline_jobs.failed ? 'warning' : 'success'}
          loading={loading}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="admin-card p-5">
          <h2 className="text-base font-bold text-ink">Nội dung chờ xử lý</h2>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Link to="/admin/briefs" className="rounded-control border border-border bg-background/80 p-4 transition hover:border-primary/30 hover:bg-primary-soft/40">
              <p className="text-xs font-bold uppercase tracking-wide text-muted">Briefs</p>
              <p className="mt-1 text-2xl font-extrabold text-ink">{loading ? '—' : fmt(summary?.content_briefs.pending_review)}</p>
              <p className="mt-1 text-sm text-muted">draft / review</p>
            </Link>
            <Link to="/admin/suggestions" className="rounded-control border border-border bg-background/80 p-4 transition hover:border-accent/30 hover:bg-accent-soft/50">
              <p className="text-xs font-bold uppercase tracking-wide text-muted">Đính chính sẵn sàng</p>
              <p className="mt-1 text-2xl font-extrabold text-ink">{loading ? '—' : fmt(summary?.content_briefs.ready_suggestions)}</p>
              <p className="mt-1 text-sm text-muted">status = ready</p>
            </Link>
          </div>
        </div>

        <div className="admin-card p-5">
          <h2 className="text-base font-bold text-ink">Thao tác nhanh</h2>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {[
              { to: '/alerts', label: 'Xử lý cảnh báo', icon: WarningCircle, tone: 'text-destructive' },
              { to: '/van-ban', label: 'Số hóa văn bản', icon: Article, tone: 'text-primary' },
              { to: '/social', label: 'Crawl MXH', icon: ShareNetwork, tone: 'text-accent' },
              { to: '/qa', label: 'QA nội bộ', icon: ListMagnifyingGlass, tone: 'text-success' },
            ].map(({ to, label, icon: IconCmp, tone }) => (
              <Link
                key={to}
                to={to}
                className="group flex items-center gap-3 rounded-control border border-border bg-background/80 p-3.5 transition hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-lift"
              >
                <div className={`flex h-10 w-10 items-center justify-center rounded-[12px] bg-white shadow-sm ${tone}`}>
                  <IconCmp size={20} weight="fill" aria-hidden />
                </div>
                <span className="flex-1 text-sm font-bold text-ink">{label}</span>
                <ArrowRight size={16} className="text-muted opacity-0 transition group-hover:opacity-100" aria-hidden />
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
