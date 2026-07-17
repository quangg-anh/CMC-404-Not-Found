import { useState } from 'react';
import { UploadSimple, FilePdf, FileDoc, Checks, CircleDashed, CheckCircle, Clock } from '@phosphor-icons/react';

interface JobStatus {
  id: string;
  stage: 'uploading' | 'parsing' | 'extracting' | 'graphing' | 'completed' | 'error';
  progress: number;
  filename: string;
}

export default function IngestPage() {
  const [isDragging, setIsDragging] = useState(false);
  const [currentJob, setCurrentJob] = useState<JobStatus | null>(null);

  // Mock Handle Upload
  const handleSimulateUpload = () => {
    setCurrentJob({ id: 'JOB-9812', stage: 'uploading', progress: 10, filename: 'Luat-Dat-Dai-2024.pdf' });
    
    // Simulate pipeline steps
    setTimeout(() => setCurrentJob(p => p ? { ...p, stage: 'parsing', progress: 35 } : null), 2000);
    setTimeout(() => setCurrentJob(p => p ? { ...p, stage: 'extracting', progress: 65 } : null), 4500);
    setTimeout(() => setCurrentJob(p => p ? { ...p, stage: 'graphing', progress: 85 } : null), 7000);
    setTimeout(() => setCurrentJob(p => p ? { ...p, stage: 'completed', progress: 100 } : null), 9000);
  };

  const steps = [
    { key: 'uploading', label: 'Tải lên & Quét Virus' },
    { key: 'parsing', label: 'Bóc tách Điều/Khoản (Parser)' },
    { key: 'extracting', label: 'Trích xuất Thực thể (LLM)' },
    { key: 'graphing', label: 'Xây dựng Đồ thị (Neo4j)' }
  ];

  const getStepStatus = (stepIndex: number, currentStage: string) => {
    const stages = ['uploading', 'parsing', 'extracting', 'graphing', 'completed'];
    const currentIndex = stages.indexOf(currentStage);
    
    if (currentIndex > stepIndex) return 'completed';
    if (currentIndex === stepIndex) return 'processing';
    return 'pending';
  };

  return (
    <div className="max-w-4xl mx-auto pb-20 animate-fade-in-up">
      <div className="mb-10">
        <h1 className="text-3xl font-black text-slate-900 tracking-tight mb-2">Số hóa Văn bản Pháp luật</h1>
        <p className="text-slate-500 font-medium">
          Nạp văn bản mới vào cơ sở dữ liệu. AI sẽ tự động bóc tách cấu trúc và xây dựng Đồ thị Tri thức.
        </p>
      </div>

      {!currentJob || currentJob.stage === 'error' ? (
        <div 
          className={`border-2 border-dashed rounded-[32px] p-12 text-center transition-all duration-300 ${
            isDragging 
              ? 'border-brand bg-brand/5 scale-[1.02]' 
              : 'border-slate-300 bg-white hover:border-brand/50 hover:bg-slate-50'
          }`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => { e.preventDefault(); setIsDragging(false); handleSimulateUpload(); }}
        >
          <div className="w-20 h-20 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-6 text-brand">
            <UploadSimple size={40} weight="bold" />
          </div>
          <h3 className="text-xl font-bold text-slate-800 mb-2">Kéo thả file PDF hoặc DOCX vào đây</h3>
          <p className="text-slate-500 font-medium mb-8">Hỗ trợ file tối đa 50MB. Văn bản sẽ được quét OCR nếu là bản scan.</p>
          
          <div className="flex items-center justify-center gap-4 mb-8">
            <div className="flex items-center gap-2 px-4 py-2 bg-slate-100 rounded-lg text-sm font-semibold text-slate-600">
              <FilePdf size={20} className="text-red-500" weight="fill" /> PDF
            </div>
            <div className="flex items-center gap-2 px-4 py-2 bg-slate-100 rounded-lg text-sm font-semibold text-slate-600">
              <FileDoc size={20} className="text-blue-500" weight="fill" /> DOCX
            </div>
          </div>
          
          <button 
            onClick={handleSimulateUpload}
            className="bg-slate-900 text-white font-bold px-8 py-3.5 rounded-xl hover:bg-brand transition-colors shadow-lg shadow-slate-900/10"
          >
            Chọn file từ máy tính
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-[32px] border border-slate-200 shadow-xl shadow-slate-200/50 p-8">
          {/* Job Header */}
          <div className="flex items-center justify-between mb-10 pb-6 border-b border-slate-100">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <span className="bg-slate-100 text-slate-500 text-xs font-bold px-2 py-1 rounded">ID: {currentJob.id}</span>
                {currentJob.stage === 'completed' ? (
                  <span className="bg-emerald-50 text-emerald-600 text-xs font-bold px-2 py-1 rounded flex items-center gap-1"><Checks size={14} /> Hoàn tất</span>
                ) : (
                  <span className="bg-brand/10 text-brand text-xs font-bold px-2 py-1 rounded flex items-center gap-1"><CircleDashed size={14} className="animate-spin" /> Đang xử lý</span>
                )}
              </div>
              <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                <FilePdf size={24} className="text-red-500" weight="fill" /> {currentJob.filename}
              </h2>
            </div>
            
            <div className="text-right">
              <div className="text-3xl font-black text-brand mb-1">{currentJob.progress}%</div>
              <div className="w-48 h-2 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full bg-brand transition-all duration-500 ease-out" style={{ width: `${currentJob.progress}%` }}></div>
              </div>
            </div>
          </div>

          {/* Stepper */}
          <div className="relative">
            <div className="absolute left-6 top-6 bottom-6 w-0.5 bg-slate-100"></div>
            <div className="space-y-8 relative z-10">
              {steps.map((step, idx) => {
                const status = getStepStatus(idx, currentJob.stage);
                return (
                  <div key={step.key} className="flex items-center gap-6">
                    {status === 'completed' ? (
                      <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-500 flex items-center justify-center border-2 border-emerald-500">
                        <CheckCircle size={24} weight="fill" />
                      </div>
                    ) : status === 'processing' ? (
                      <div className="w-12 h-12 rounded-full bg-white text-brand flex items-center justify-center border-2 border-brand shadow-[0_0_15px_rgba(220,38,38,0.2)]">
                        <CircleDashed size={24} className="animate-spin" />
                      </div>
                    ) : (
                      <div className="w-12 h-12 rounded-full bg-slate-50 text-slate-300 flex items-center justify-center border-2 border-slate-200">
                        <Clock size={24} weight="bold" />
                      </div>
                    )}
                    
                    <div>
                      <h4 className={`font-bold text-lg ${status === 'pending' ? 'text-slate-400' : 'text-slate-900'}`}>
                        {step.label}
                      </h4>
                      {status === 'processing' && <p className="text-sm font-medium text-brand mt-1">Đang thực thi pipeline...</p>}
                      {status === 'completed' && <p className="text-sm font-medium text-slate-500 mt-1">Hoàn tất thành công</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {currentJob.stage === 'completed' && (
            <div className="mt-10 pt-8 border-t border-slate-100 flex justify-end gap-4">
              <button onClick={() => setCurrentJob(null)} className="px-6 py-2.5 rounded-xl font-bold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors">
                Nạp file khác
              </button>
              <button className="px-6 py-2.5 rounded-xl font-bold text-white bg-slate-900 hover:bg-brand transition-colors">
                Xem kết quả bóc tách
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
