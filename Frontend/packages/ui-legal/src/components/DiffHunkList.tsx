import React from 'react';
import { PlusCircle, MinusCircle, Link as LinkIcon, MagicWand } from '@phosphor-icons/react';

export interface DiffHunk {
  id: string;
  type: 'added' | 'removed' | 'modified';
  oldText?: string;
  newText?: string;
  method: 'exact' | 'similarity';
}

interface DiffHunkListProps {
  hunks: DiffHunk[];
}

export const DiffHunkList: React.FC<DiffHunkListProps> = ({ hunks }) => {
  return (
    <div className="space-y-4">
      {hunks.map((hunk) => (
        <div key={hunk.id} className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden flex flex-col group">
          <div className="bg-slate-50 px-4 py-2 border-b border-slate-100 flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1">
              {hunk.type === 'modified' ? 'Sửa đổi' : hunk.type === 'added' ? 'Bổ sung mới' : 'Bãi bỏ'}
            </span>
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-brand bg-brand/5 px-2 py-1 rounded border border-brand/10">
              {hunk.method === 'exact' ? <LinkIcon size={12} weight="bold" /> : <MagicWand size={12} weight="bold" />}
              {hunk.method === 'exact' ? 'Dẫn chiếu tường minh' : 'Phân tích ngữ nghĩa AI'}
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100">
            {/* Old Version */}
            <div className={`p-5 ${hunk.type === 'added' ? 'bg-slate-50/50 flex items-center justify-center text-slate-400 italic text-sm' : ''}`}>
              {hunk.type === 'added' ? (
                'Không có trong văn bản cũ'
              ) : (
                <div className="flex gap-3">
                  <div className="text-red-500 mt-0.5 shrink-0"><MinusCircle size={18} weight="fill" /></div>
                  <p className="text-sm font-medium text-slate-600 leading-relaxed line-through decoration-red-200 decoration-2">
                    {hunk.oldText}
                  </p>
                </div>
              )}
            </div>

            {/* New Version */}
            <div className={`p-5 ${hunk.type === 'removed' ? 'bg-slate-50/50 flex items-center justify-center text-slate-400 italic text-sm' : 'bg-emerald-50/30'}`}>
              {hunk.type === 'removed' ? (
                'Đã bãi bỏ trong văn bản mới'
              ) : (
                <div className="flex gap-3">
                  <div className="text-emerald-500 mt-0.5 shrink-0"><PlusCircle size={18} weight="fill" /></div>
                  <p className="text-sm font-medium text-slate-800 leading-relaxed">
                    {hunk.newText}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
