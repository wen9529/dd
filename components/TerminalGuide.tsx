import React, { useState } from 'react';
import { askTermuxHelp } from '../services/geminiService';
import { SendIcon } from './Icons';

export const TerminalGuide: React.FC = () => {
  const [query, setQuery] = useState('');
  const [history, setHistory] = useState<{ q: string; a: string }[]>([]);
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    if (!query.trim()) return;
    setLoading(true);
    
    // Add temp placeholder
    const currentQuery = query;
    setQuery('');

    try {
      const answer = await askTermuxHelp(currentQuery);
      setHistory(prev => [...prev, { q: currentQuery, a: answer }]);
    } catch (e) {
      setHistory(prev => [...prev, { q: currentQuery, a: "获取答案时出错。" }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#111] p-6">
      <h2 className="text-2xl font-bold text-white mb-6">Termux 助手</h2>
      
      <div className="flex-1 overflow-y-auto space-y-6 pr-4 mb-4">
        {history.length === 0 && (
          <div className="text-center text-gray-600 mt-20">
            <h3 className="text-lg font-medium mb-2">关于 Termux 有什么可以帮你的吗？</h3>
            <p className="text-sm">试着问：</p>
            <ul className="text-sm space-y-2 mt-4">
              <li>"如何安装 python？"</li>
              <li>"如何访问手机存储？"</li>
              <li>"如何让机器人在后台持续运行？"</li>
            </ul>
          </div>
        )}
        
        {history.map((item, idx) => (
          <div key={idx} className="flex flex-col gap-2">
            <div className="self-end bg-gray-800 text-white px-4 py-2 rounded-2xl rounded-tr-none max-w-[80%]">
              {item.q}
            </div>
            <div className="self-start bg-termux-dim text-gray-200 px-4 py-3 rounded-2xl rounded-tl-none max-w-[90%] border border-gray-700">
               <div className="whitespace-pre-wrap text-sm leading-relaxed prose prose-invert prose-code:text-termux-accent prose-code:bg-black/50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded">
                 {/* Basic markdown rendering for code blocks */}
                 {item.a.split('```').map((part, i) => {
                     if (i % 2 === 1) { // Code block
                         return (
                            <div key={i} className="my-2 bg-black p-3 rounded border border-gray-800 font-mono text-xs text-termux-accent overflow-x-auto">
                                {part.trim()}
                            </div>
                         );
                     }
                     return <span key={i}>{part}</span>;
                 })}
               </div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="self-start bg-termux-dim px-4 py-3 rounded-2xl rounded-tl-none border border-gray-700 w-24">
             <div className="flex gap-1 justify-center">
               <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
               <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-75"></div>
               <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-150"></div>
             </div>
          </div>
        )}
      </div>

      <div className="relative">
        <input
          type="text"
          className="w-full bg-[#1e1e1e] border border-gray-800 rounded-full py-3 px-6 pr-12 text-white focus:outline-none focus:border-termux-accent transition-colors"
          placeholder="输入关于 Termux 的问题..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
        />
        <button
          onClick={handleAsk}
          disabled={loading || !query.trim()}
          className="absolute right-2 top-2 p-1.5 bg-termux-accent text-black rounded-full hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <SendIcon className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
};
