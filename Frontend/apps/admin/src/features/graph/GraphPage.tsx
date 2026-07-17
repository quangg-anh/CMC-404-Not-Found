import React, { useState, useRef, useEffect, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { apiGet } from '../../lib/api';
import { ShareNetwork, MagnifyingGlass, Funnel, Info, FileText, Article, ShieldWarning, HandCoins, Calendar, Warning } from '@phosphor-icons/react';

// Mock Ontology Data matching BE1 specifications
const mockData = {
  nodes: [
    { id: 'VB1', name: 'Nghị định 100/2019/NĐ-CP', type: 'VanBan', val: 12 },
    { id: 'D5', name: 'Điều 5. Xử phạt người điều khiển xe ô tô', type: 'Dieu', val: 8 },
    { id: 'D6', name: 'Điều 6. Xử phạt người điều khiển mô tô', type: 'Dieu', val: 8 },
    { id: 'K1_D5', name: 'Khoản 1 (Phạt 200k - 400k)', type: 'Khoan', val: 5 },
    { id: 'K2_D5', name: 'Khoản 2 (Phạt 400k - 600k)', type: 'Khoan', val: 5 },
    { id: 'K6_D5', name: 'Khoản 6 (Phạt 6tr - 8tr)', type: 'Khoan', val: 5 },
    { id: 'K10_D5', name: 'Khoản 10 (Phạt 30tr - 40tr, Nồng độ cồn)', type: 'Khoan', val: 5 },
    
    // Entities
    { id: 'HV1', name: 'Không chấp hành hiệu lệnh đèn tín hiệu', type: 'HanhViCam', val: 4 },
    { id: 'HV2', name: 'Trong máu có nồng độ cồn > 80mg/100ml', type: 'HanhViCam', val: 4 },
    { id: 'CT1', name: 'Phạt tiền 6.000.000đ - 8.000.000đ', type: 'CheTai', val: 4 },
    { id: 'CT2', name: 'Phạt tiền 30.000.000đ - 40.000.000đ', type: 'CheTai', val: 4 },
    { id: 'CT3', name: 'Tước GPLX 22 - 24 tháng', type: 'CheTai', val: 4 },
    { id: 'CT4', name: 'Tạm giữ phương tiện 7 ngày', type: 'CheTai', val: 4 }
  ],
  links: [
    { source: 'VB1', target: 'D5', label: 'CO_DIEU' },
    { source: 'VB1', target: 'D6', label: 'CO_DIEU' },
    { source: 'D5', target: 'K1_D5', label: 'CO_KHOAN' },
    { source: 'D5', target: 'K2_D5', label: 'CO_KHOAN' },
    { source: 'D5', target: 'K6_D5', label: 'CO_KHOAN' },
    { source: 'D5', target: 'K10_D5', label: 'CO_KHOAN' },
    
    { source: 'K6_D5', target: 'HV1', label: 'QUY_DINH' },
    { source: 'K6_D5', target: 'CT1', label: 'QUY_DINH' },
    
    { source: 'K10_D5', target: 'HV2', label: 'QUY_DINH' },
    { source: 'K10_D5', target: 'CT2', label: 'QUY_DINH' },
    { source: 'K10_D5', target: 'CT3', label: 'QUY_DINH' },
    { source: 'K10_D5', target: 'CT4', label: 'QUY_DINH' },
  ]
};

const NODE_COLORS: Record<string, string> = {
  VanBan: '#1e293b', // slate-800
  Dieu: '#3b82f6',   // blue-500
  Khoan: '#0ea5e9',  // sky-500
  HanhViCam: '#ef4444', // red-500
  CheTai: '#f59e0b',    // amber-500
  NghiaVu: '#8b5cf6',   // violet-500
  QuyenLoi: '#10b981',  // emerald-500
};

const NODE_ICONS: Record<string, React.FC<any>> = {
  VanBan: FileText,
  Dieu: Article,
  Khoan: Article,
  HanhViCam: ShieldWarning,
  CheTai: HandCoins,
};

export default function GraphPage() {
  const [containerDimensions, setContainerDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>();
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  const [graphData, setGraphData] = useState<any>(mockData);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // 1. Fetch real graph data from backend
    setIsLoading(true);
    apiGet('/admin/graph')
      .then((res: any) => {
        if (res && res.nodes && res.nodes.length > 0) {
          setGraphData({
            nodes: res.nodes.map((n: any) => ({ ...n, val: n.val || 5 })),
            links: res.links || []
          });
        }
      })
      .catch((err) => {
        console.warn('Backend chưa sẵn sàng API Đồ thị, đang dùng Mock Data làm fallback:', err);
      })
      .finally(() => {
        setIsLoading(false);
      });

    // 2. Setup responsive dimensions
    const updateDimensions = () => {
      if (containerRef.current) {
        setContainerDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
      }
    };
    
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    
    // Zoom to fit after a short delay
    setTimeout(() => {
      if (fgRef.current) {
        fgRef.current.zoomToFit(400, 50);
      }
    }, 500);

    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node);
    
    // Center map on node
    if (fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 1000);
      fgRef.current.zoom(4, 1000);
    }
  }, [fgRef]);

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const label = node.name;
    const fontSize = 12 / globalScale;
    const color = NODE_COLORS[node.type] || '#cbd5e1';
    
    const nodeRadius = node.val || 4;

    // Draw Node Circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, nodeRadius, 0, 2 * Math.PI, false);
    ctx.fillStyle = color;
    ctx.fill();
    
    // Draw Stroke if selected
    if (selectedNode && selectedNode.id === node.id) {
      ctx.lineWidth = 2 / globalScale;
      ctx.strokeStyle = '#0f172a';
      ctx.stroke();
    }
    
    // Draw Label
    if (globalScale > 1.5 || node.val > 6) {
      ctx.font = `${fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#1e293b';
      
      // Background for text
      const textWidth = ctx.measureText(label).width;
      const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2); 
      
      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.fillRect(
        node.x - bckgDimensions[0] / 2, 
        node.y + nodeRadius + 3, 
        bckgDimensions[0], 
        bckgDimensions[1]
      );

      ctx.fillStyle = '#0f172a';
      ctx.fillText(label, node.x, node.y + nodeRadius + 3 + fontSize/2);
    }
  }, [selectedNode]);

  return (
    <div className="h-full flex flex-col">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ShareNetwork size={28} weight="fill" className="text-primary" />
            Đồ thị Tri thức (Knowledge Graph)
            {isLoading && <span className="ml-3 text-xs bg-primary/10 text-primary font-bold px-2 py-1 rounded animate-pulse">Đang tải data...</span>}
          </h1>
          <p className="text-slate-500 text-sm mt-1">Trực quan hóa cấu trúc và các thực thể pháp lý được bóc tách từ văn bản.</p>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative">
            <input 
              type="text" 
              placeholder="Tìm kiếm node..."
              className="pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-sm w-64 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
            />
            <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
          </div>
          <button className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors">
            <Funnel size={16} /> Lọc
          </button>
        </div>
      </div>

      <div className="flex-1 flex gap-6 min-h-[600px]">
        {/* Graph Canvas */}
        <div 
          className="flex-1 bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative"
          ref={containerRef}
        >
          {containerDimensions.width > 0 && (
            <ForceGraph2D
              ref={fgRef}
              width={containerDimensions.width}
              height={containerDimensions.height}
              graphData={graphData}
              nodeLabel="name"
              nodeColor={(node: any) => NODE_COLORS[node.type] || '#cbd5e1'}
              nodeRelSize={1}
              nodeCanvasObject={paintNode}
              onNodeClick={handleNodeClick}
              linkColor={() => '#cbd5e1'}
              linkDirectionalArrowLength={3.5}
              linkDirectionalArrowRelPos={1}
              linkWidth={1.5}
            />
          )}
          
          {/* Legend Overlay */}
          <div className="absolute bottom-4 left-4 bg-white/90 backdrop-blur-sm p-3 rounded-lg shadow-sm border border-slate-200/50 flex flex-col gap-2 text-xs">
            <div className="font-semibold text-slate-700 mb-1">Loại Node</div>
            {Object.entries(NODE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }}></div>
                <span className="text-slate-600">{type}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Info Panel */}
        <div className="w-[320px] bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col">
          <div className="p-4 border-b border-slate-100 bg-slate-50/50 rounded-t-xl">
            <h3 className="font-semibold text-slate-900 flex items-center gap-2">
              <Info size={18} className="text-slate-400" />
              Chi tiết Node
            </h3>
          </div>
          
          <div className="p-4 flex-1 overflow-y-auto">
            {selectedNode ? (
              <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                <div className="flex items-start gap-3">
                  <div 
                    className="w-10 h-10 rounded-lg flex items-center justify-center text-white shrink-0 mt-1 shadow-sm"
                    style={{ backgroundColor: NODE_COLORS[selectedNode.type] || '#94a3b8' }}
                  >
                    {NODE_ICONS[selectedNode.type] ? (
                      React.createElement(NODE_ICONS[selectedNode.type], { size: 20, weight: 'fill' })
                    ) : (
                      <ShareNetwork size={20} weight="fill" />
                    )}
                  </div>
                  <div>
                    <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">{selectedNode.type}</div>
                    <h4 className="text-base font-bold text-slate-900 leading-snug">{selectedNode.name}</h4>
                  </div>
                </div>

                <div className="space-y-4 pt-4 border-t border-slate-100">
                  <div>
                    <div className="text-xs font-semibold text-slate-500 mb-1">Canonical ID</div>
                    <code className="text-xs bg-slate-100 px-2 py-1 rounded text-slate-700 font-mono">
                      {selectedNode.id}
                    </code>
                  </div>
                  
                  {selectedNode.type === 'HanhViCam' && (
                    <div className="bg-red-50 p-3 rounded-lg border border-red-100">
                      <div className="flex items-center gap-2 text-red-600 font-semibold text-sm mb-1">
                        <Warning size={16} weight="fill" /> Thuộc tính mở rộng
                      </div>
                      <div className="text-sm text-red-900/80">
                        <span className="font-semibold">Mức độ rủi ro:</span> Cao<br/>
                        <span className="font-semibold">Cần trích xuất:</span> 100%
                      </div>
                    </div>
                  )}

                  <div>
                    <div className="text-xs font-semibold text-slate-500 mb-2">Quan hệ (Edges)</div>
                    <div className="space-y-2 text-sm">
                      {graphData.links.filter((l: any) => (l.source as any).id === selectedNode.id || l.source === selectedNode.id).map((link: any, idx: number) => (
                        <div key={`out-${idx}`} className="flex items-center gap-2 text-slate-600">
                          <span className="text-xs bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">OUT</span>
                          <span className="text-primary font-mono text-xs">{link.label}</span>
                          <span className="truncate">&rarr; {(link.target as any).name || link.target}</span>
                        </div>
                      ))}
                      {graphData.links.filter((l: any) => (l.target as any).id === selectedNode.id || l.target === selectedNode.id).map((link: any, idx: number) => (
                        <div key={`in-${idx}`} className="flex items-center gap-2 text-slate-600">
                          <span className="text-xs bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">IN</span>
                          <span className="text-primary font-mono text-xs">{link.label}</span>
                          <span className="truncate">&larr; {(link.source as any).name || link.source}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 space-y-3">
                <ShareNetwork size={48} weight="light" className="text-slate-300" />
                <p className="text-sm">Chọn một Node trên đồ thị để xem chi tiết thông tin và các mối quan hệ liên quan.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
