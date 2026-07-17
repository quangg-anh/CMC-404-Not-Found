import React from 'react';
import { WarningCircle, CheckCircle, Question } from '@phosphor-icons/react';

export type RiskLabel = 'khop' | 'mau_thuan' | 'khong_ro';

interface RiskBadgeProps {
  label: RiskLabel;
  confidence?: 'high' | 'medium' | 'low';
}

export const RiskBadge: React.FC<RiskBadgeProps> = ({ label, confidence }) => {
  const config = {
    khop: {
      color: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      icon: <CheckCircle size={14} weight="fill" />,
      text: 'Khớp với quy định đã liên kết'
    },
    mau_thuan: {
      color: 'bg-red-50 text-red-700 border-red-200',
      icon: <WarningCircle size={14} weight="fill" />,
      text: 'Có dấu hiệu mâu thuẫn'
    },
    khong_ro: {
      color: 'bg-amber-50 text-amber-700 border-amber-200',
      icon: <Question size={14} weight="fill" />,
      text: 'Chưa đủ căn cứ'
    }
  };

  const current = config[label];

  return (
    <div className="flex items-center gap-2">
      <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold border ${current.color}`}>
        {current.icon}
        {current.text}
      </div>
      {confidence && (
        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
          {confidence === 'high' ? 'Tin cậy cao' : confidence === 'medium' ? 'Tin cậy trung bình' : 'Tin cậy thấp'}
        </span>
      )}
    </div>
  );
};
