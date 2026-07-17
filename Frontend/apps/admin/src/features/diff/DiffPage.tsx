import { useState } from 'react';
import { GitDiff, ArrowsLeftRight, CaretDown, FileText } from '@phosphor-icons/react';
import { DiffHunkList, type DiffHunk } from '../../../../../packages/ui-legal/src/components/DiffHunkList';

export default function DiffPage() {
  const [mockHunks] = useState<DiffHunk[]>([
    {
      id: 'hunk-1',
      type: 'modified',
      method: 'similarity',
      oldText: 'Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng đối với người điều khiển xe mô tô trên đường mà trong máu hoặc hơi thở có nồng độ cồn chưa vượt quá 50 miligam/100 mililít máu.',
      newText: 'Phạt tiền từ 3.000.000 đồng đến 4.000.000 đồng đối với người điều khiển xe mô tô trên đường mà trong máu hoặc hơi thở có nồng độ cồn chưa vượt quá 50 miligam/100 mililít máu.'
    },
    {
      id: 'hunk-2',
      type: 'added',
      method: 'exact',
      newText: 'Tạm giữ phương tiện vi phạm tối đa 07 ngày làm việc để ngăn chặn ngay hành vi vi phạm có nguy cơ gây tai nạn nghiêm trọng.'
    },
    {
      id: 'hunk-3',
      type: 'removed',
      method: 'similarity',
      oldText: 'Trường hợp người vi phạm không mang theo giấy phép lái xe thì chỉ bị phạt cảnh cáo.'
    }
  ]);

  return (
    <div className="max-w-6xl mx-auto pb-20 animate-fade-in-up">
      <div className="mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold uppercase tracking-widest mb-3">
          <GitDiff size={16} weight="fill" /> Version Control Pháp lý
        </div>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight mb-2">So sánh Văn bản (Diff)</h1>
        <p className="text-slate-500 font-medium">
          Đối chiếu tự động Điểm/Khoản/Điều giữa hai phiên bản luật cũ và mới để tìm ra chính xác những điểm thay đổi.
        </p>
      </div>

      {/* Selectors */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm mb-10 flex flex-col md:flex-row items-center gap-6">
        <div className="flex-1 w-full">
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Văn bản gốc (Cũ)</label>
          <div className="relative">
            <button className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 flex items-center justify-between text-left hover:border-brand/30 transition-colors">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded bg-slate-200 text-slate-500 flex items-center justify-center shrink-0"><FileText size={16} /></div>
                <div>
                  <div className="font-bold text-slate-800 line-clamp-1">Nghị định 100/2019/NĐ-CP</div>
                  <div className="text-xs text-slate-500 font-medium mt-0.5">Ban hành: 30/12/2019</div>
                </div>
              </div>
              <CaretDown size={16} className="text-slate-400" />
            </button>
          </div>
        </div>

        <div className="w-12 h-12 shrink-0 bg-slate-100 rounded-full flex items-center justify-center text-slate-400 border border-slate-200 md:mt-6">
          <ArrowsLeftRight size={20} weight="bold" />
        </div>

        <div className="flex-1 w-full">
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Văn bản mới (Thay thế/Sửa đổi)</label>
          <div className="relative">
            <button className="w-full bg-emerald-50/30 border border-emerald-200 rounded-xl px-4 py-3 flex items-center justify-between text-left hover:border-emerald-300 transition-colors">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0"><FileText size={16} /></div>
                <div>
                  <div className="font-bold text-slate-800 line-clamp-1">Nghị định 123/2021/NĐ-CP</div>
                  <div className="text-xs text-slate-500 font-medium mt-0.5">Ban hành: 28/12/2021</div>
                </div>
              </div>
              <CaretDown size={16} className="text-slate-400" />
            </button>
          </div>
        </div>
      </div>

      {/* Diff View */}
      <div className="space-y-6">
        <div className="flex items-center justify-between border-b border-slate-200 pb-4">
          <h3 className="text-lg font-bold text-slate-900">Chi tiết thay đổi</h3>
          <div className="flex gap-4 text-xs font-bold text-slate-500">
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-emerald-500"></span> Thêm mới (1)</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-red-500"></span> Bãi bỏ (1)</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-amber-500"></span> Sửa đổi (1)</span>
          </div>
        </div>

        <DiffHunkList hunks={mockHunks} />
      </div>

    </div>
  );
}
