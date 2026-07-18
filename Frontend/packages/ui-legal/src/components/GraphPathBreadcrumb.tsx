import React, { useState } from 'react';
import { CaretDown, CaretUp, Graph } from '@phosphor-icons/react';

interface GraphNode {
  id?: string;
  type?: string;
  label?: string;
  title?: string;
  text?: string;
}
interface GraphPathObj {
  khoan_id?: string;
  nodes?: GraphNode[];
  edges?: unknown[];
}
interface GraphPathBreadcrumbProps {
  // The backend may send graph_paths as pre-formatted strings ("A → B → C") or as structured
  // objects ({khoan_id, nodes, edges}). Accept anything and normalize so rendering never crashes.
  paths?: unknown[];
}

function dieuNumber(label?: string, id?: string): string {
  const raw = (label || '').trim();
  if (raw && !raw.includes('::') && !/^D\d+/i.test(raw)) return raw;
  const fromLabel = raw.match(/D(\d+)/i);
  if (fromLabel) return fromLabel[1];
  const fromId = (id || '').match(/::D(\d+)/i);
  return fromId?.[1] || raw || '';
}

function nodeLabel(n: GraphNode): string {
  const t = (n.type || '').toLowerCase();
  if (t === 'dieu') {
    const num = dieuNumber(n.label, n.id);
    return num ? `Điều ${num}` : 'Điều';
  }
  if (t === 'khoan') {
    if (n.title && !n.title.includes('::')) return n.title;
    const m = (n.label || n.id || '').match(/\.?K(\d+)/i);
    return m ? `Khoản ${m[1]}` : 'Khoản';
  }
  return n.title || n.label || n.id || '—';
}

// Normalize any accepted path shape into an array of readable node labels.
function toNodeLabels(path: unknown): string[] {
  if (typeof path === 'string') return path.split('→').map((n) => n.trim()).filter(Boolean);
  const obj = path as GraphPathObj | null;
  if (obj && Array.isArray(obj.nodes)) return obj.nodes.map(nodeLabel).filter(Boolean);
  return [];
}

export const GraphPathBreadcrumb: React.FC<GraphPathBreadcrumbProps> = ({ paths }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const chains = (paths ?? []).map(toNodeLabels).filter((c) => c.length > 0);
  if (chains.length === 0) return null;

  return (
    <div className="mt-4 border border-slate-200/60 rounded-xl bg-slate-50/50 overflow-hidden transition-all duration-300">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-100/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Graph size={16} weight="bold" className="text-brand" />
          <span className="text-[13px] font-bold text-slate-700">Luồng truy xuất Đồ thị tri thức (Graph Paths)</span>
          <span className="bg-brand/10 text-brand px-2 py-0.5 rounded-md text-[10px] font-black">{chains.length}</span>
        </div>
        {isExpanded ? (
          <CaretUp size={16} weight="bold" className="text-slate-400" />
        ) : (
          <CaretDown size={16} weight="bold" className="text-slate-400" />
        )}
      </button>

      {isExpanded && (
        <div className="px-4 pb-4 pt-1 border-t border-slate-100 space-y-2">
          {chains.map((nodes, idx) => (
            <div key={idx} className="flex flex-wrap items-center gap-1.5 text-xs font-medium">
              {nodes.map((node, nIdx) => (
                <React.Fragment key={nIdx}>
                  <span className="bg-white border border-slate-200 px-2.5 py-1 rounded-md text-slate-700 shadow-sm">
                    {node}
                  </span>
                  {nIdx < nodes.length - 1 && <span className="text-slate-300 select-none">→</span>}
                </React.Fragment>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
