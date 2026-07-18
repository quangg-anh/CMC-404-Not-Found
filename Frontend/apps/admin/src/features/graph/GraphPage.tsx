import React, { useState, useRef, useEffect, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { apiGet } from '../../lib/api';
import {
  ShareNetwork, MagnifyingGlass, Info, FileText, Article, ShieldWarning, HandCoins, Warning,
  Spinner, TreeStructure, Gauge, ArrowsOut, FrameCorners, Eye, EyeSlash, ArrowClockwise,
} from '@phosphor-icons/react';

interface GraphNode {
  id: string; type: string; raw_type?: string; label?: string; short_label?: string;
  importance_score: number; connection_count: number; centrality: number; size: number;
  properties?: Record<string, unknown>;
}
interface GraphEdge { source: string; target: string; type: string }
interface NeighborhoodResponse {
  seed_id: string; depth: number; nodes: GraphNode[]; edges: GraphEdge[];
  meta?: { total_nodes: number; returned_nodes: number; truncated: boolean; layout_hint: string };
}
interface SeedSuggestion { id: string; type: string; label: string; degree: number }
interface SeedResponse { items: SeedSuggestion[]; total: number }

interface ClarityItem { khoan_id: string; noi_dung: string; mau_thuan: number; khong_ro: number; volume: number; clarity_risk: number }
interface ClarityResponse { min_volume: number; items: ClarityItem[]; total: number }

const NODE_COLORS: Record<string, string> = {
  van_ban: '#2557D6', chuong: '#1E46B8', dieu: '#4F7FE8', khoan: '#0EA5E9', chu_de: '#E85D0F',
  VanBanPhapLuat: '#1E3A8A',
  VanBan: '#1E3A8A',
  Dieu: '#2557D6',
  Khoan: '#0EA5E9',
  ChuThe: '#6366F1',
  NghiaVu: '#7C3AED',
  QuyenLoi: '#168A45',
  HanhViCam: '#DC2626',
  CheTai: '#B54708',
  ThoiHan: '#14B8A6',
  ChuDe: '#E85D0F',
  BaiDang: '#2557D6',
  YKien: '#F08A4B',
};

const NODE_ICONS: Record<string, React.FC<any>> = {
  VanBanPhapLuat: FileText,
  VanBan: FileText,
  Dieu: Article,
  Khoan: Article,
  HanhViCam: ShieldWarning,
  CheTai: HandCoins,
};

type FgNode = {
  id: string; name: string; shortLabel: string; type: string; rawType?: string; val: number;
  importanceScore: number; connectionCount: number; centrality: number; isMostImportant?: boolean;
  properties?: Record<string, unknown>; x?: number; y?: number;
};
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
  const [mode, setMode] = useState<'overview' | 'detail'>('overview');
  const [nodeLimit, setNodeLimit] = useState(50);
  const [showLabels, setShowLabels] = useState(true);
  const [graphMeta, setGraphMeta] = useState<NeighborhoodResponse['meta']>();
  const [graphData, setGraphData] = useState<{ nodes: FgNode[]; links: FgLink[] }>({ nodes: [], links: [] });
  const [selectedNode, setSelectedNode] = useState<FgNode | null>(null);
  const [seeds, setSeeds] = useState<SeedSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dims, setDims] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);

  const fetchGraph = useCallback((seedId: string, d: number) => {
    if (!seedId.trim()) { setError('Nhập một seed ID (vb_id / khoan_id / slug) để khám phá.'); return; }
    setLoading(true);
    setError(null);
    const effectiveDepth = mode === 'overview' ? 1 : d;
    apiGet<NeighborhoodResponse>(`/admin/graph/neighborhood?seed_id=${encodeURIComponent(seedId.trim())}&depth=${effectiveDepth}&limit=${nodeLimit}`)
      .then((res) => {
        const sourceNodes = res.nodes ?? [];
        const highestImportance = Math.max(0, ...sourceNodes.map((n) => n.importance_score || 0));
        const nodes: FgNode[] = sourceNodes.map((n) => ({
          id: n.id, name: n.label || n.id, shortLabel: n.short_label || n.label || n.id,
          type: n.type, rawType: n.raw_type,
          val: (n.importance_score || 0) === highestImportance && highestImportance > 0
            ? 34
            : Math.max(n.type === 'van_ban' ? 18 : 7, (n.size || (n.type === 'van_ban' ? 44 : 18)) / 2),
          importanceScore: n.importance_score || 0, connectionCount: n.connection_count || 0,
          centrality: n.centrality || 0,
          isMostImportant: (n.importance_score || 0) === highestImportance && highestImportance > 0,
          properties: n.properties,
        }));
        const links: FgLink[] = (res.edges ?? []).map((e) => ({ source: e.source, target: e.target, label: e.type }));
        setGraphData({ nodes, links });
        setGraphMeta(res.meta);
        setSelectedNode(null);
        if (nodes.length === 0) setError('Không tìm thấy nút nào cho seed này trong đồ thị.');
        setTimeout(() => fgRef.current?.zoomToFit(650, 110), 700);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Lỗi tải đồ thị'))
      .finally(() => setLoading(false));
  }, [mode, nodeLimit]);

  useEffect(() => {
    apiGet<SeedResponse>('/admin/graph/seeds?limit=12')
      .then((res) => {
        const list = res.items ?? [];
        setSeeds(list);
      })
      .catch(() => setSeeds([]));
  }, []);

  useEffect(() => {
    const update = () => containerRef.current && setDims({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  useEffect(() => {
    if (graphData.nodes.length === 0 || !fgRef.current) return;
    fgRef.current.d3Force('charge')?.strength(mode === 'overview' ? -650 : -520).distanceMax(850);
    fgRef.current.d3Force('link')?.distance(mode === 'overview' ? 160 : 125).strength(0.2);
    fgRef.current.d3Force('center')?.strength?.(0.035);
    fgRef.current.d3ReheatSimulation();
  }, [graphData.nodes.length, mode]);

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node);
    if (Number.isFinite(node.x) && Number.isFinite(node.y)) {
      fgRef.current?.centerAt(node.x, node.y, 800);
    }
    fgRef.current?.zoom(4, 800);
  }, []);

  const relatedIds = React.useMemo(() => {
    if (!selectedNode) return null;
    const ids = new Set<string>([selectedNode.id]);
    graphData.links.forEach((link: any) => {
      const source = String(link.source?.id ?? link.source);
      const target = String(link.target?.id ?? link.target);
      if (source === selectedNode.id) ids.add(target);
      if (target === selectedNode.id) ids.add(source);
    });
    return ids;
  }, [graphData.links, selectedNode]);

  const relayout = useCallback(() => {
    graphData.nodes.forEach((node: any) => { node.fx = undefined; node.fy = undefined; });
    fgRef.current?.d3ReheatSimulation();
    setTimeout(() => fgRef.current?.zoomToFit(600, 80), 700);
  }, [graphData.nodes]);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) containerRef.current?.requestFullscreen();
    else document.exitFullscreen();
  }, []);

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const x = Number(node.x);
    const y = Number(node.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const scale = Number.isFinite(globalScale) && globalScale > 0 ? globalScale : 1;
    const label = String(node.shortLabel ?? node.name ?? node.id ?? '');
    const fontSize = 12 / scale;
    const color = node.isMostImportant ? '#f97316' : (NODE_COLORS[node.type] || '#94a3b8');
    const rawRadius = Number(node.val);
    const r = Number.isFinite(rawRadius) && rawRadius > 0 ? Math.min(rawRadius, 80) : 4;
    if (graphData.nodes.length <= 120 && (node.isMostImportant || node.type === 'van_ban' || node.importanceScore >= 35)) {
      const halo = ctx.createRadialGradient(x, y, r * 0.4, x, y, r * 1.8);
      halo.addColorStop(0, node.isMostImportant ? 'rgba(249,115,22,.55)' : `${color}3d`);
      halo.addColorStop(1, `${color}00`);
      ctx.beginPath();
      ctx.arc(x, y, r * 1.8, 0, 2 * Math.PI);
      ctx.fillStyle = halo;
      ctx.fill();
    }
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI, false);
    ctx.globalAlpha = relatedIds && !relatedIds.has(node.id) ? 0.14 : 1;
    ctx.fillStyle = color;
    ctx.fill();
    ctx.lineWidth = (node.isMostImportant ? 5 : node.type === 'van_ban' ? 3 : 1.2) / scale;
    ctx.strokeStyle = node.isMostImportant ? '#fef3c7' : node.type === 'van_ban' ? '#ffffff' : `${color}cc`;
    ctx.stroke();
    if (selectedNode && selectedNode.id === node.id) {
      ctx.lineWidth = 2 / scale;
      ctx.strokeStyle = '#0f172a';
      ctx.stroke();
    }
    if (showLabels && (scale > 1.35 || node.isMostImportant || node.type === 'van_ban' || node.importanceScore >= 35)) {
      ctx.font = `${node.isMostImportant ? '700 ' : ''}${node.isMostImportant ? fontSize * 1.25 : fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.lineWidth = 3 / scale;
      ctx.strokeStyle = 'rgba(255,255,255,.95)';
      ctx.strokeText(label.length > 40 ? label.slice(0, 40) + '…' : label, x, y + r + fontSize);
      ctx.fillStyle = node.isMostImportant ? '#c2410c' : '#334155';
      ctx.fillText(label.length > 40 ? label.slice(0, 40) + '…' : label, x, y + r + fontSize);
    }
    ctx.globalAlpha = 1;
  }, [graphData.nodes.length, relatedIds, selectedNode, showLabels]);

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
        <select value={nodeLimit} onChange={(e) => setNodeLimit(Number(e.target.value))} className="px-3 py-2.5 bg-white border border-slate-200 rounded-lg text-sm font-semibold focus:outline-none" title="Giới hạn node render">
          {[50, 80, 120, 200, 300].map((value) => <option key={value} value={value}>{value} node</option>)}
        </select>
        <button onClick={() => fetchGraph(seed, depth)} disabled={loading} className="px-5 py-2.5 bg-slate-900 text-white rounded-lg text-sm font-bold hover:bg-primary transition-colors flex items-center gap-2 disabled:opacity-50">
          {loading ? <Spinner size={16} className="animate-spin" /> : <TreeStructure size={16} weight="bold" />} Khám phá
        </button>
      </div>

      <div className="mb-4 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1">
          {(['overview', 'detail'] as const).map((value) => (
            <button key={value} onClick={() => setMode(value)} className={`px-3 py-1.5 rounded-lg text-xs font-bold ${mode === value ? 'bg-white text-primary shadow-sm' : 'text-slate-500'}`}>
              {value === 'overview' ? 'Tổng quan' : 'Chi tiết'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => fgRef.current?.zoomToFit(500, 80)} className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold flex items-center gap-1.5"><FrameCorners size={15} /> Fit màn hình</button>
          <button onClick={relayout} className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold flex items-center gap-1.5"><ArrowClockwise size={15} /> Sắp xếp lại</button>
          <button onClick={() => setShowLabels((value) => !value)} className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold flex items-center gap-1.5">{showLabels ? <EyeSlash size={15} /> : <Eye size={15} />} Nhãn</button>
          <button onClick={toggleFullscreen} className="p-2 bg-white border border-slate-200 rounded-lg" title="Toàn màn hình"><ArrowsOut size={16} /></button>
        </div>
      </div>

      {error && <div className="mb-4 bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium">{error}</div>}

      {seeds.length > 0 && (
        <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
          {seeds.map((item) => (
            <button
              key={item.id}
              onClick={() => { setSeed(item.id); fetchGraph(item.id, depth); }}
              className="shrink-0 px-3 py-2 rounded-xl bg-white border border-slate-200 hover:border-primary/40 hover:bg-primary/5 transition-colors text-left min-w-[220px]"
            >
              <div className="text-[11px] font-bold text-primary uppercase">{item.type} · {item.degree} cạnh</div>
              <div className="text-sm font-semibold text-slate-800 truncate">{item.label}</div>
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 flex gap-6 min-h-[560px]">
        <div
          className="flex-1 bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative"
          ref={containerRef}
          style={{ backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(148,163,184,.18) 1px, transparent 0)', backgroundSize: '24px 24px' }}
        >
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
              linkColor={(link: any) => {
                if (!relatedIds) return 'rgba(148,163,184,.32)';
                const source = String(link.source?.id ?? link.source);
                const target = String(link.target?.id ?? link.target);
                return relatedIds.has(source) && relatedIds.has(target) ? 'rgba(52,71,103,.62)' : 'rgba(148,163,184,.08)';
              }}
              linkDirectionalArrowLength={2.5}
              linkDirectionalArrowRelPos={1}
              linkWidth={() => relatedIds ? 1.4 : 0.8}
              linkCurvature={0.04}
              cooldownTicks={graphData.nodes.length > 120 ? 80 : 120}
              d3AlphaDecay={0.025}
              d3VelocityDecay={0.4}
              onBackgroundClick={() => setSelectedNode(null)}
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
          {graphMeta && (
            <div className="absolute top-4 left-4 rounded-lg border border-slate-200 bg-white/90 px-3 py-2 text-xs font-semibold text-slate-600 shadow-sm backdrop-blur-sm">
              {graphMeta.returned_nodes}/{graphMeta.total_nodes} node
              {graphMeta.truncated && <span className="ml-2 text-amber-600">Đã giới hạn</span>}
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
                  <div className="grid grid-cols-3 gap-2">
                    {[['Quan trọng', selectedNode.importanceScore.toFixed(1)], ['Liên kết', selectedNode.connectionCount], ['Centrality', selectedNode.centrality.toFixed(3)]].map(([label, value]) => (
                      <div key={label} className="rounded-lg bg-slate-50 p-2 text-center"><div className="text-sm font-black text-primary">{value}</div><div className="text-[10px] text-slate-500">{label}</div></div>
                    ))}
                  </div>
                  {selectedNode.properties && Object.keys(selectedNode.properties).length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-slate-500 mb-2">Thuộc tính</div>
                      <div className="space-y-1.5 text-xs">
                        {Object.entries(selectedNode.properties).slice(0, 10).map(([key, value]) => (
                          <div key={key} className="grid grid-cols-[88px_1fr] gap-2">
                            <span className="font-semibold text-slate-500 truncate">{key}</span>
                            <span className="text-slate-700 break-words">{String(value).slice(0, 180)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
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
