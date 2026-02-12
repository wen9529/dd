import React, { useState, useEffect } from 'react';
import { generateBotCode } from '../services/geminiService';
import { BotProject } from '../types';
import { SendIcon, CopyIcon, PlusIcon, SettingsIcon } from './Icons';
import { Terminal } from './Terminal';

interface BotGeneratorProps {
  onSaveProject: (project: BotProject) => void;
}

export const BotGenerator: React.FC<BotGeneratorProps> = ({ onSaveProject }) => {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);
  const [dependencies, setDependencies] = useState<string[]>([]);
  const [explanation, setExplanation] = useState<string>('');
  const [hasConfig, setHasConfig] = useState(false);
  
  // Terminal Simulation State
  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<'code' | 'terminal'>('code');

  useEffect(() => {
    // 检查是否有配置
    const token = localStorage.getItem('bot_token');
    setHasConfig(!!token);
  }, []);

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setGeneratedCode(null);
    setTerminalLines([]);

    // 读取配置
    const token = localStorage.getItem('bot_token') || undefined;
    const ownerId = localStorage.getItem('bot_owner_id') || undefined;

    try {
      const result = await generateBotCode(prompt, { token, ownerId });
      setGeneratedCode(result.code);
      setExplanation(result.explanation);
      setDependencies(result.dependencies);
      
      // 自动填充模拟终端
      const installCmds = [
        "apt update && apt upgrade -y",
        "pkg install python",
        "pip install --upgrade pip",
        ...result.dependencies.map(d => `pip install ${d}`)
      ];
      setTerminalLines(installCmds);

    } catch (err) {
      console.error(err);
      setExplanation("生成代码失败。请检查您的 API Key 并重试。");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = () => {
    if (!generatedCode) return;
    const newProject: BotProject = {
      id: Date.now().toString(),
      name: prompt.slice(0, 20) + (prompt.length > 20 ? '...' : ''),
      description: explanation.slice(0, 100),
      code: generatedCode,
      dependencies,
      createdAt: Date.now(),
    };
    onSaveProject(newProject);
    alert('项目已保存到仪表盘！');
  };

  const copyToClipboard = () => {
    if (generatedCode) {
      navigator.clipboard.writeText(generatedCode);
      alert('代码已复制到剪贴板');
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#111] text-white p-6 gap-6">
      
      {/* Input Section */}
      <div className="flex flex-col gap-4">
        <div className="flex justify-between items-center">
            <h2 className="text-2xl font-bold bg-gradient-to-r from-termux-accent to-emerald-600 bg-clip-text text-transparent">
            机器人生成器
            </h2>
            {!hasConfig && (
                <div className="flex items-center gap-2 text-xs text-yellow-500 bg-yellow-500/10 px-3 py-1 rounded border border-yellow-500/20">
                    <span>未检测到 Token，建议先去设置</span>
                </div>
            )}
            {hasConfig && (
                <div className="flex items-center gap-2 text-xs text-termux-accent bg-termux-accent/10 px-3 py-1 rounded border border-termux-accent/20">
                    <span>已启用自动 Token 注入</span>
                </div>
            )}
        </div>
        
        <div className="relative">
          <textarea
            className="w-full bg-[#1e1e1e] border border-gray-800 rounded-lg p-4 text-gray-200 focus:outline-none focus:border-termux-accent transition-colors resize-none h-32"
            placeholder="描述你的机器人功能... (例如：'一个能够回显消息并欢迎新用户的机器人')"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <button
            onClick={handleGenerate}
            disabled={loading}
            className={`absolute bottom-4 right-4 bg-termux-accent text-black px-4 py-2 rounded-md font-bold flex items-center gap-2 hover:bg-emerald-400 transition-all ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {loading ? (
              <span className="animate-spin h-5 w-5 border-2 border-black border-t-transparent rounded-full"></span>
            ) : (
              <>
                <SendIcon className="w-4 h-4" /> 生成代码
              </>
            )}
          </button>
        </div>
      </div>

      {/* Output Section */}
      {generatedCode && (
        <div className="flex-1 flex flex-col min-h-0 gap-4">
          <div className="flex items-center justify-between">
            <div className="flex gap-2">
              <button
                onClick={() => setActiveTab('code')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'code' ? 'bg-gray-800 text-white' : 'text-gray-500 hover:text-gray-300'}`}
              >
                生成的代码
              </button>
              <button
                onClick={() => setActiveTab('terminal')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'terminal' ? 'bg-gray-800 text-white' : 'text-gray-500 hover:text-gray-300'}`}
              >
                Termux 安装指南
              </button>
            </div>
            
            <div className="flex gap-2">
               <button
                onClick={copyToClipboard}
                className="bg-[#222] hover:bg-[#333] border border-gray-700 text-gray-300 px-3 py-1.5 rounded-md text-sm flex items-center gap-2 transition-colors"
              >
                <CopyIcon className="w-4 h-4" /> 复制
              </button>
               <button
                onClick={handleSave}
                className="bg-[#222] hover:bg-[#333] border border-gray-700 text-gray-300 px-3 py-1.5 rounded-md text-sm flex items-center gap-2 transition-colors"
              >
                <PlusIcon className="w-4 h-4" /> 保存项目
              </button>
            </div>
          </div>

          <div className="flex-1 min-h-0 bg-[#1e1e1e] rounded-lg border border-gray-800 overflow-hidden relative">
            {activeTab === 'code' ? (
              <pre className="h-full overflow-auto p-4 text-sm font-mono text-gray-300">
                <code>{generatedCode}</code>
              </pre>
            ) : (
              <div className="h-full flex flex-col p-4 gap-4 overflow-y-auto">
                <div className="bg-blue-900/20 border border-blue-900/50 p-4 rounded-md">
                   <h3 className="text-blue-400 font-bold mb-2">设置说明</h3>
                   <p className="text-gray-400 text-sm">{explanation}</p>
                </div>
                
                <div className="flex-1">
                   <h4 className="text-gray-400 mb-2 text-xs uppercase tracking-wider">模拟 Termux 安装过程</h4>
                   <div className="h-64">
                       <Terminal lines={terminalLines} />
                   </div>
                </div>

                <div className="bg-[#111] p-4 rounded-md border border-gray-800">
                   <h4 className="text-gray-400 mb-2 text-xs uppercase tracking-wider">所需依赖库</h4>
                   <div className="flex flex-wrap gap-2">
                       {dependencies.map(dep => (
                           <span key={dep} className="px-2 py-1 bg-gray-800 text-termux-accent text-xs rounded font-mono">
                               {dep}
                           </span>
                       ))}
                   </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {!generatedCode && !loading && (
        <div className="flex-1 flex items-center justify-center text-gray-600 flex-col gap-4">
          <div className="w-16 h-16 rounded-full bg-gray-900 flex items-center justify-center">
             <BotIcon className="w-8 h-8 text-gray-700" />
          </div>
          <p>在上方描述你的机器人逻辑以生成 Python 脚本。</p>
        </div>
      )}
    </div>
  );
};

const BotIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><rect x="3" y="11" width="18" height="10" rx="2"></rect><circle cx="12" cy="5" r="2"></circle><path d="M12 7v4"></path><line x1="8" y1="16" x2="8" y2="16"></line><line x1="16" y1="16" x2="16" y2="16"></line></svg>
);