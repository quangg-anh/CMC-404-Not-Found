import React, { useState, useRef, useEffect, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { apiGet } from '../../lib/api';
import {
  ShareNetwork, MagnifyingGlass, Info, FileText, Article, ShieldWarning, HandCoins, Warning,
  Spinner, TreeStructure, Gauge,
} from '@phosphor-icons/react';

interface GraphNode { id: string; type: string; label?: string; properties?: Record<string, unknown> }
interface GraphEdge { source: string; target: string; type: string }
interface NeighborhoodResponse { seed_id: string; depth: number; nodes: GraphNode[]; edges: GraphEdge[] }

interface ClarityItem { khoan_id: string; noi_dung: string; mau_thuan: number; khong_ro: number; volume: number; clarity_risk: number }
interface ClarityResponse { min_volume: number; items: ClarityItem[]; total: number }

const NODE_COLORS: Record<string, string> = {
  VanBanPhapLuat: '#1e293b',
  VanBan: '#1e293b',
  Dieu: '#3b82f6',
  Khoan: '#0ea5e9',
  ChuThe: '#8b5cf6',
  NghiaVu: '#8b5cf6',
  QuyenLoi: '#10b981',
  HanhViCam: '#ef4444',
  CheTai: '#f59e0b',
  ThoiHan: '#14b8a6',
  ChuDe: '#ec4899',
  BaiDang: '#6366f1',
  YKien: '#f97316',
};

const NODE_ICONS: Record<string, React.FC<any>> = {
  VanBanPhapLuat: FileText,
  VanBan: FileText,
  Dieu: Article,
  Khoan: Article,
  HanhViCam: ShieldWarning,
  CheTai: HandCoins,
};

type FgNode = { id: string; name: string; type: string; val: number; x?: number; y?: number };
type FgLink = { source: string; target: string; label: string };

export default function GraphPage() {
  const [tab, setTab] = useState<'explore' | 'clarity'>('explore');
  return (
    <div className="h-full flex flex-col">
      <div className="mb-6 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ShareNetwork size={28} weight="fill" className="text-primary" /> Đồ thị Tri thức (Knowledge Graph)
          </h1>
          <p className="text-slate-500 text-sm mt-1">Khám phá quan hệ pháp lý trong Neo4j và phát hiện điều khoản đang bị hiểu sai nhiều nhất.</p>
        </div>
        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl">
          {([['explore', 'Khám phá', TreeStructure], ['clarity', 'Chỉ số Mù mờ', Gauge]] as const).map(([id, label, Icon]) => (
            <button key={id} onClick={() => setTab(id)} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-all ${tab === id ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}>
              <Icon size={16} weight={tab === id ? 'fill' : 'regular'} /> {label}
            </button>
          ))}
        </div>
      </div>
      {tab === 'explore' ? <ExploreTab /> : <ClarityTab />}
    </div>
  );
}

function ExploreTab() {
  const [seed, setSeed] = useState('');
  const [depth, setDepth] = useState(1);
  const [graphData, setGraphData] = useState<{ nodes: FgNode[]; links: FgLink[] }>({ nodes: [], links: [] });
  const [selectedNode, setSelectedNode] = useState<FgNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dims, setDims] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);

  const fetchGraph = useCallback((seedId: string, d: number) => {
    if (!seedId.trim()) { setError('Nhập một seed ID (vb_id / khoan_id / slug) để khám phá.'); return; }
    setLoading(true);
    setError(null);
    apiGet<NeighborhoodResponse>(`/admin/graph/neighborhood?seed_id=${encodeURIComponent(seedId.trim())}&depth=${d}`)
      .then((res) => {
        const nodes: FgNode[] = (res.nodes ?? []).map((n) => ({ id: n.id, name: n.label || n.id, type: n.type, val: 5 }));
        const links: FgLink[] = (res.edges ?? []).map((e) => ({ source: e.source, target: e.target, label: e.type }));
        setGraphData({ nodes, links });
        if (nodes.length === 0) setError('Không tìm thấy nút nào cho seed này trong đồ thị.');
        setTimeout(() => fgRef.current?.zoomToFit(400, 60), 400);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Lỗi tải đồ thị'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const update = () => containerRef.current && setDims({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node);
    fgRef.current?.centerAt(node.x, node.y, 800);
    fgRef.current?.zoom(4, 800);
  }, []);

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const label = node.name;
    const fontSize = 12 / globalScale;
    const color = NODE_COLORS[node.type] || '#94a3b8';
    const r = node.val || 4;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
    ctx.fillStyle = color;
    ctx.fill();
    if (selectedNode && selectedNode.id === node.id) {
      ctx.lineWidth = 2 / globalScale;
      ctx.strokeStyle = '#0f172a';
      ctx.stroke();
    }
    if (globalScale > 1.4) {
      ctx.font = `${fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#0f172a';
      ctx.fillText(label.length > 40 ? label.slice(0, 40) + '…' : label, node.x, node.y + r + fontSize);
    }
  }, [selectedNode]);

  return (
    <>
      <div className="mb-4 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[280px]">
          <input
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetchGraph(seed, depth)}
            placeholder="Seed ID: vb_id, khoan_id, hoặc slug (VD: 15/2020/ND-CP)"
            className="w-full pl-9 pr-4 py-2.5 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
          <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
        </div>
        <select value={depth} onChange={(e) => setDepth(Number(e.target.value))} className="px-3 py-2.5 bg-white border border-slate-200 rounded-lg text-sm font-semibold focus:outline-none">
          <option value={1}>Độ sâu 1</option>
          <option value={2}>Độ sâu 2</option>
        </select>
        <button onClick={() => fetchGraph(seed, depth)} disabled={loading} className="px-5 py-2.5 bg-slate-900 text-white rounded-lg text-sm font-bold hover:bg-primary transition-colors flex items-center gap-2 disabled:opacity-50">
          {loading ? <Spinner size={16} className="animate-spin" /> : <TreeStructure size={16} weight="bold" />} Khám phá
        </button>
      </div>

      {error && <div className="mb-4 bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium">{error}</div>}

      <div className="flex-1 flex gap-6 min-h-[560px]">
        <div className="flex-1 bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative" ref={containerRef}>
          {graphData.nodes.length > 0 ? (
            <ForceGraph2D
              ref={fgRef}
              width={dims.width}
              height={dims.height}
              graphData={graphData}
              nodeLabel="name"
              nodeColor={(n: any) => NODE_COLORS[n.type] || '#94a3b8'}
              nodeRelSize={1}
              nodeCanvasObject={paintNode}
              onNodeClick={handleNodeClick}
              linkColor={() => '#cbd5e1'}
              linkDirectionalArrowLength={3.5}
              linkDirectionalArrowRelPos={1}
              linkWidth={1.5}
            />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 space-y-3 p-8">
              <ShareNetwork size={48} weight="light" className="text-slate-300" />
              <p className="text-sm max-w-xs">Nhập một seed ID rồi bấm “Khám phá” để trực quan hóa vùng lân cận của nút trong đồ thị Neo4j.</p>
            </div>
          )}
          {graphData.nodes.length > 0 && (
            <div className="absolute bottom-4 left-4 bg-white/90 backdrop-blur-sm p-3 rounded-lg shadow-sm border border-slate-200/50 flex flex-col gap-1.5 text-xs max-h-[240px] overflow-y-auto">
              <div className="font-semibold text-slate-700 mb-1">Loại Node</div>
              {Array.from(new Set(graphData.nodes.map((n) => n.type))).map((type) => (
                <div key={type} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NODE_COLORS[type] || '#94a3b8' }} />
                  <span className="text-slate-600">{type}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="w-[320px] bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col">
          <div className="p-4 border-b border-slate-100 bg-slate-50/50 rounded-t-xl">
            <h3 className="font-semibold text-slate-900 flex items-center gap-2"><Info size={18} className="text-slate-400" /> Chi tiết Node</h3>
          </div>
          <div className="p-4 flex-1 overflow-y-auto">
            {selectedNode ? (
              <div className="space-y-6">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center text-white shrink-0 mt-1 shadow-sm" style={{ backgroundColor: NODE_COLORS[selectedNode.type] || '#94a3b8' }}>
                    {NODE_ICONS[selectedNode.type] ? React.createElement(NODE_ICONS[selectedNode.type], { size: 20, weight: 'fill' }) : <ShareNetwork size={20} weight="fill" />}
                  </div>
                  <div>
                    <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">{selectedNode.type}</div>
                    <h4 className="text-base font-bold text-slate-900 leading-snug">{selectedNode.name}</h4>
                  </div>
                </div>
                <div className="space-y-4 pt-4 border-t border-slate-100">
                  <div>
                    <div className="text-xs font-semibold text-slate-500 mb-1">Canonical ID</div>
                    <code className="text-xs bg-slate-100 px-2 py-1 rounded text-slate-700 font-mono break-all">{selectedNode.id}</code>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-slate-500 mb-2">Quan hệ (Edges)</div>
                    <div className="space-y-2 text-sm">
                      {graphData.links.filter((l: any) => (l.source?.id ?? l.source) === selectedNode.id).map((link: any, idx) => (
                        <div key={`out-${idx}`} className="flex items-center gap-2 text-slate-600">
                          <span className="text-xs bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">OUT</span>
                          <span className="text-primary font-mono text-xs">{link.label}</span>
                          <span className="truncate">&rarr; {(link.target?.name ?? link.target)}</span>
                        </div>
                      ))}
                      {graphData.links.filter((l: any) => (l.target?.id ?? l.target) === selectedNode.id).map((link: any, idx) => (
                        <div key={`in-${idx}`} className="flex items-center gap-2 text-slate-600">
                          <span className="text-xs bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">IN</span>
                          <span className="text-primary font-mono text-xs">{link.label}</span>
                          <span className="truncate">&larr; {(link.source?.name ?? link.source)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 space-y-3">
                <ShareNetwork size={48} weight="light" className="text-slate-300" />
                <p className="text-sm">Chọn một Node để xem chi tiết và các mối quan hệ.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function ClarityTab() {
  const [items, setItems] = useState<ClarityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minVolume, setMinVolume] = useState(5);

  const load = useCallback((mv: number) => {
    setLoading(true);
    apiGet<ClarityResponse>(`/admin/graph/clarity-index?min_volume=${mv}`)
      .then((d) => { setItems(d.items ?? []); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Lỗi tải chỉ số'))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => load(minVolume), [load, minVolume]);

  const riskColor = (r: number) => (r >= 0.66 ? 'bg-red-500' : r >= 0.33 ? 'bg-amber-500' : 'bg-emerald-500');
  const riskText = (r: number) => (r >= 0.66 ? 'text-red-600' : r >= 0.33 ? 'text-amber-600' : 'text-emerald-600');

  return (
    <div className="flex-1">
      <div className="bg-violet-50 border border-violet-200 rounded-2xl p-5 mb-6 flex items-start gap-4">
        <Gauge size={28} weight="fill" className="text-violet-500 shrink-0 mt-0.5" />
        <div>
          <h3 className="font-bold text-violet-900">Chỉ số Mù mờ Pháp lý</h3>
          <p className="text-sm text-violet-700 leading-relaxed mt-1">
            Tổng hợp quan hệ <code className="font-mono">DOI_CHIEU</code> từ ý kiến người dân để tìm điều khoản bị hiểu theo nhiều hướng (mâu thuẫn / không rõ).
            Đây là tín hiệu truyền thông — không phải kết luận rằng luật viết sai.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-600">
          Ngưỡng tối thiểu
          <select value={minVolume} onChange={(e) => setMinVolume(Number(e.target.value))} className="px-2 py-1 bg-white border border-slate-200 rounded-lg text-sm">
            {[1, 3, 5, 10, 20].map((v) => <option key={v} value={v}>{v} lượt đối chiếu</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="p-12 text-center text-slate-400 font-semibold flex items-center justify-center gap-2"><Spinner size={20} className="animate-spin" /> Đang tính chỉ số…</div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm font-semibold">{error}</div>
      ) : items.length === 0 ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200">
          <Gauge size={40} className="text-slate-300 mx-auto mb-4" weight="fill" />
          <p className="text-slate-500 font-semibold">Chưa đủ dữ liệu đối chiếu để xếp hạng.</p>
          <p className="text-slate-400 text-sm mt-1">Chỉ số xuất hiện khi có đủ ý kiến MXH liên kết tới các Khoản.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((it, i) => (
            <div key={it.khoan_id ?? i} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4 mb-3">
                <div className="min-w-0">
                  <code className="text-xs font-mono text-primary bg-primary/5 px-2 py-0.5 rounded">{it.khoan_id}</code>
                  <p className="text-sm text-slate-700 mt-2 leading-relaxed line-clamp-2">{it.noi_dung}</p>
                </div>
                <div className="text-right shrink-0">
                  <div className={`text-2xl font-black ${riskText(it.clarity_risk)}`}>{Math.round(it.clarity_risk * 100)}%</div>
                  <div className="text-xs text-slate-400 font-semibold">rủi ro mù mờ</div>
                </div>
              </div>
              <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden mb-2">
                <div className={`h-full rounded-full ${riskColor(it.clarity_risk)}`} style={{ width: `${it.clarity_risk * 100}%` }} />
              </div>
              <div className="flex items-center gap-4 text-xs font-semibold text-slate-500">
                <span className="flex items-center gap-1 text-red-600"><Warning size={13} weight="fill" /> {it.mau_thuan} mâu thuẫn</span>
                <span className="flex items-center gap-1 text-amber-600">{it.khong_ro} không rõ</span>
                <span className="ml-auto">{it.volume} lượt đối chiếu</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
