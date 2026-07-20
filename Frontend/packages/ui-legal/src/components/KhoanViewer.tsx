import React from 'react';
import { FileText, BookmarkSimple } from '@phosphor-icons/react';

interface KhoanViewerProps {
  vanBanSoHieu: string;
  dieuKhoan: string;
  noiDung: string;
  highlightText?: string;
  effectiveFrom?: string;
  effectiveTo?: string;
  versionNo?: number;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function formatDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('vi-VN');
}

export const KhoanViewer: React.FC<KhoanViewerProps> = ({
  vanBanSoHieu,
  dieuKhoan,
  noiDung,
  highlightText,
  effectiveFrom,
  effectiveTo,
  versionNo,
}) => {
  const renderContent = () => {
    if (!highlightText) return <p className="text-slate-700 leading-relaxed">{noiDung}</p>;

    const parts = noiDung.split(new RegExp(`(${escapeRegExp(highlightText)})`, 'gi'));
    return (
      <p className="text-slate-700 leading-relaxed">
        {parts.map((part, i) =>
          part.toLowerCase() === highlightText.toLowerCase()
            ? <mark key={i} className="bg-yellow-200/80 text-slate-900 rounded-sm px-1 font-medium">{part}</mark>
            : part
        )}
      </p>
    );
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
      <div className="bg-slate-50/80 border-b border-slate-100 px-5 py-3.5 flex flex-wrap gap-4 items-center justify-between">
        <div className="flex items-center gap-2">
          <BookmarkSimple size={18} className="text-brand" weight="fill" />
          <span className="font-bold text-slate-800">{dieuKhoan}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {effectiveFrom ? (
            <span className="rounded-md border border-blue-100 bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">
              Hiệu lực {formatDate(effectiveFrom)} – {effectiveTo ? formatDate(effectiveTo) : 'hiện tại'}
            </span>
          ) : null}
          {versionNo ? <span className="rounded-md bg-slate-200/70 px-2 py-1 text-xs font-bold text-slate-600">V{versionNo}</span> : null}
          <div className="flex items-center gap-1.5 text-xs font-bold text-slate-500 bg-white px-2.5 py-1 rounded-md border border-slate-200">
            <FileText size={14} /> {vanBanSoHieu}
          </div>
        </div>
      </div>
      <div className="p-6">
        {renderContent()}
      </div>
    </div>
  );
};
