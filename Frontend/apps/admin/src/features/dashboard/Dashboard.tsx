import { WarningCircle, TrendUp, Article, ShareNetwork, ListMagnifyingGlass, ArrowUpRight } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';

export default function DashboardPage() {
  return (
    <div className="space-y-6 max-w-6xl">
      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-surface rounded-2xl p-6 shadow-soft">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-muted text-sm font-bold mb-1">Văn bản đã xử lý</p>
              <h3 className="text-3xl font-bold text-primary">1,204</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-gradient-accent text-white flex items-center justify-center shadow-md">
              <Article size={24} weight="fill" />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-sm">
            <span className="text-success font-bold flex items-center"><ArrowUpRight size={14} className="mr-0.5"/>+12%</span>
            <span className="text-muted font-medium">tháng này</span>
          </div>
        </div>
        
        <div className="bg-surface rounded-2xl p-6 shadow-soft relative overflow-hidden">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-muted text-sm font-bold mb-1">Cảnh báo sai lệch</p>
              <h3 className="text-3xl font-bold text-primary">42</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-gradient-danger text-white flex items-center justify-center shadow-md">
              <WarningCircle size={24} weight="fill" />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-sm">
            <span className="text-destructive font-bold">3 vụ việc</span>
            <span className="text-muted font-medium">cần xử lý ngay</span>
          </div>
        </div>

        <div className="bg-surface rounded-2xl p-6 shadow-soft">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-muted text-sm font-bold mb-1">Độ chính xác (QA)</p>
              <h3 className="text-3xl font-bold text-primary">99.8%</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-gradient-success text-white flex items-center justify-center shadow-md">
              <TrendUp size={24} weight="fill" />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-sm">
            <span className="text-success font-bold flex items-center"><ArrowUpRight size={14} className="mr-0.5"/>+0.5%</span>
            <span className="text-muted font-medium">tháng này</span>
          </div>
        </div>
      </div>

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
          <button className="flex flex-col items-center justify-center p-6 bg-background rounded-2xl hover:shadow-card transition-shadow border border-transparent hover:border-border group">
            <div className="w-14 h-14 bg-surface rounded-xl flex items-center justify-center shadow-soft mb-4 group-hover:-translate-y-1 transition-transform">
              <ShareNetwork size={28} className="text-accent" weight="fill" />
            </div>
            <span className="text-sm font-bold text-primary">Đồ thị liên kết</span>
          </button>
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
