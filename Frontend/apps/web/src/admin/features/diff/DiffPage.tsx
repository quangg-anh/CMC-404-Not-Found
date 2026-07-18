import { useState } from 'react';
import { GitDiff, ArrowsLeftRight, Spinner } from '@phosphor-icons/react';
import { DiffHunkList, type DiffHunk } from '../../../../../../packages/ui-legal/src/components/DiffHunkList';
import { apiPost } from '../../../lib/api';

interface BackendHunk {
  type: 'replace' | 'delete' | 'insert';
  old: string;
  new: string;
}

interface DiffResponse {
  hunks: BackendHunk[];
  method: string;
  total_hunks: number;
}



function mapType(t: BackendHunk['type']): DiffHunk['type'] {
  if (t === 'insert') return 'added';
  if (t === 'delete') return 'removed';
  return 'modified';
}

export default function DiffPage() {
  const [oldText, setOldText] = useState('');
  const [newText, setNewText] = useState('');
  const [hunks, setHunks] = useState<DiffHunk[]>([]);
  const [method, setMethod] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasRun, setHasRun] = useState(false);

  const runDiff = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiPost<DiffResponse>('/admin/legal/diff', { old_text: oldText, new_text: newText, method: 'auto' });
      const mapped: DiffHunk[] = (data.hunks ?? []).map((h, i) => ({
        id: `hunk-${i}`,
        type: mapType(h.type),
        oldText: h.old || undefined,
        newText: h.new || undefined,
        method: 'similarity',
      }));
      setHunks(mapped);
      setMethod(data.method);
      setHasRun(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi khi so sánh văn bản');
    } finally {
      setLoading(false);
    }
  };

  const counts = {
    added: hunks.filter((h) => h.type === 'added').length,
    removed: hunks.filter((h) => h.type === 'removed').length,
    modified: hunks.filter((h) => h.type === 'modified').length,
  };

  return (
    <div className="max-w-6xl mx-auto pb-20 animate-fade-in-up">
      <div className="mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold uppercase tracking-widest mb-3">
          <GitDiff size={16} weight="fill" /> Version Control Pháp lý
        </div>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight mb-2">So sánh Văn bản (Diff)</h1>
        <p className="text-slate-500 font-medium">
          Đối chiếu tự động nội dung Điểm/Khoản/Điều giữa hai phiên bản để tìm ra chính xác những điểm thay đổi.
        </p>
      </div>

      {/* Inputs */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm mb-6 flex flex-col md:flex-row items-stretch gap-6">
        <div className="flex-1 w-full">
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Văn bản gốc (Cũ)</label>
          <textarea
            value={oldText}
            onChange={(e) => setOldText(e.target.value)}
            rows={6}
            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-brand/40 focus:ring-2 focus:ring-brand/10 transition-all resize-y"
          />
        </div>

        <div className="w-12 h-12 shrink-0 bg-slate-100 rounded-full flex items-center justify-center text-slate-400 border border-slate-200 self-center">
          <ArrowsLeftRight size={20} weight="bold" />
        </div>

        <div className="flex-1 w-full">
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Văn bản mới (Thay thế/Sửa đổi)</label>
          <textarea
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            rows={6}
            className="w-full bg-emerald-50/30 border border-emerald-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 transition-all resize-y"
          />
        </div>
      </div>

      <div className="flex justify-end mb-10">
        <button
          onClick={runDiff}
          disabled={loading || !oldText.trim() || !newText.trim()}
          className="bg-slate-900 text-white font-bold px-8 py-3 rounded-xl hover:bg-brand transition-colors shadow-lg shadow-slate-900/10 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? <Spinner size={18} className="animate-spin" /> : <GitDiff size={18} weight="bold" />}
          {loading ? 'Đang so sánh…' : 'So sánh thay đổi'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-5 py-4 text-sm font-semibold mb-6">{error}</div>
      )}

      {/* Diff View */}
      {hasRun && !error && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-slate-200 pb-4">
            <h3 className="text-lg font-bold text-slate-900">Chi tiết thay đổi {method && <span className="text-sm font-medium text-slate-400">({method})</span>}</h3>
            <div className="flex gap-4 text-xs font-bold text-slate-500">
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-emerald-500"></span> Thêm mới ({counts.added})</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-red-500"></span> Bãi bỏ ({counts.removed})</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-amber-500"></span> Sửa đổi ({counts.modified})</span>
            </div>
          </div>

          {hunks.length === 0 ? (
            <div className="text-center py-12 text-slate-400 font-semibold bg-white rounded-2xl border border-slate-200">
              Hai văn bản giống nhau — không phát hiện thay đổi nào.
            </div>
          ) : (
            <DiffHunkList hunks={hunks} />
          )}
        </div>
      )}
    </div>
  );
}
