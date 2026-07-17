import React from 'react';
import { Scales, ArrowSquareOut } from '@phosphor-icons/react';

interface CitationCardProps {
  khoan_id?: string;
  van_ban: string;
  dieu: string;
  quote: string;
  url?: string;
}

export const CitationCard: React.FC<CitationCardProps> = ({ van_ban, dieu, quote, url }) => {
  return (
    <div className="group bg-white rounded-xl border border-slate-200/80 shadow-sm hover:shadow-lg hover:shadow-brand/5 hover:border-brand/30 transition-all duration-300 overflow-hidden relative">
      <div className="absolute top-0 left-0 w-1 h-full bg-brand/20 group-hover:bg-brand transition-colors duration-300"></div>
      
      <div className="bg-slate-50/50 px-4 sm:px-5 py-3 border-b border-slate-100 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded bg-brand/10 flex items-center justify-center text-brand shrink-0">
            <Scales size={14} weight="fill" />
          </div>
          <div className="flex flex-col">
            <span className="text-xs sm:text-sm font-bold text-slate-800 leading-tight line-clamp-1">{dieu}</span>
            <span className="text-[10px] text-slate-500 font-medium line-clamp-1">{van_ban}</span>
          </div>
        </div>
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-slate-400 hover:text-brand transition-colors p-1" title="Mở chi tiết văn bản">
            <ArrowSquareOut size={16} weight="bold" />
          </a>
        )}
      </div>
      
      <div className="p-4 sm:px-5 sm:py-4">
        <div className="relative">
          <span className="absolute -left-2 -top-1 text-2xl text-slate-200 font-serif leading-none select-none">"</span>
          <p className="text-[13px] sm:text-sm font-medium text-slate-600 leading-relaxed pl-2 relative z-10 italic">
            {quote}
          </p>
          <span className="absolute -right-1 bottom-0 text-2xl text-slate-200 font-serif leading-none select-none">"</span>
        </div>
      </div>
    </div>
  );
};
