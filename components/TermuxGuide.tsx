
import React, { useState } from 'react';
import { CodeBlock } from './CodeBlock';
import { TERMUX_SETUP_SCRIPT, PYTHON_BOT_SCRIPT, GITHUB_WORKFLOW_TEMPLATE, DEFAULT_STREAM_CONFIG, GENERATE_ENV_CONTENT } from '../constants';
import { StreamConfig } from '../types';
import { Terminal, Bot, Github, Save, Shield, Download, Image as ImageIcon, Video, FileText } from 'lucide-react';

export const TermuxGuide: React.FC = () => {
  const [config, setConfig] = useState<StreamConfig>(DEFAULT_STREAM_CONFIG);
  const [activeTab, setActiveTab] = useState<'setup' | 'bot' | 'workflow' | 'env'>('setup');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setConfig(prev => ({ ...prev, [name]: value }));
  };

  const setupCode = TERMUX_SETUP_SCRIPT(config);
  const botCode = PYTHON_BOT_SCRIPT;
  const workflowCode = GITHUB_WORKFLOW_TEMPLATE(config);
  const envCode = GENERATE_ENV_CONTENT(config);

  return (
    <div className="max-w-7xl mx-auto p-6 flex flex-col lg:flex-row gap-6">
      
      {/* Config Panel */}
      <div className="w-full lg:w-1/3 bg-gray-800 p-6 rounded-xl border border-gray-700 h-fit overflow-y-auto max-h-[85vh]">
        <div className="flex items-center gap-2 mb-6 text-blue-400">
          <Save size={20} />
          <h2 className="font-bold text-white">Configuration</h2>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs text-gray-400 uppercase font-semibold">GitHub</label>
            <input name="githubUser" placeholder="Owner (e.g., myname)" value={config.githubUser} onChange={handleChange} className="input-field" />
            <input name="githubRepo" placeholder="Repo (e.g., stream-repo)" value={config.githubRepo} onChange={handleChange} className="input-field" />
            <input name="githubPat" type="password" placeholder="PAT (ghp_...)" value={config.githubPat} onChange={handleChange} className="input-field" />
          </div>

          <div className="space-y-2 pt-4 border-t border-gray-700">
            <label className="text-xs text-gray-400 uppercase font-semibold">Telegram</label>
            <input name="telegramBotToken" type="password" placeholder="Bot Token" value={config.telegramBotToken} onChange={handleChange} className="input-field" />
            <input name="telegramAdminId" placeholder="Admin ID (Numeric)" value={config.telegramAdminId} onChange={handleChange} className="input-field" />
            <input name="telegramRtmpUrl" placeholder="RTMP URL" value={config.telegramRtmpUrl} onChange={handleChange} className="input-field" />
          </div>

          <div className="space-y-2 pt-4 border-t border-gray-700">
            <label className="text-xs text-gray-400 uppercase font-semibold flex items-center gap-2"><ImageIcon size={12}/> Audio Stream Cover</label>
            <input name="defaultCoverUrl" placeholder="https://..." value={config.defaultCoverUrl} onChange={handleChange} className="input-field text-xs" />
          </div>

          <div className="space-y-2 pt-2">
            <label className="text-xs text-gray-400 uppercase font-semibold flex items-center gap-2"><Video size={12}/> Max Bitrate</label>
            <input name="videoBitrate" placeholder="6000k" value={config.videoBitrate} onChange={handleChange} className="input-field" />
            <p className="text-[10px] text-gray-500">Affects FFmpeg encoding quality (default: 6000k).</p>
          </div>

           <div className="mt-4 p-3 bg-blue-900/20 border border-blue-900/50 rounded text-xs text-blue-200">
             <Shield size={14} className="inline mr-1"/>
             Data remains local. The generated script will contain these secrets.
           </div>
        </div>
      </div>

      {/* Output Panel */}
      <div className="w-full lg:w-2/3 flex flex-col bg-gray-800 rounded-xl border border-gray-700 overflow-hidden min-h-[600px]">
        <div className="flex border-b border-gray-700 bg-gray-900/50">
          <button onClick={() => setActiveTab('setup')} className={`tab-btn ${activeTab === 'setup' ? 'active' : ''}`}>
            <Terminal size={16} /> setup.sh
          </button>
          <button onClick={() => setActiveTab('bot')} className={`tab-btn ${activeTab === 'bot' ? 'active' : ''}`}>
            <Bot size={16} /> bot.py
          </button>
          <button onClick={() => setActiveTab('env')} className={`tab-btn ${activeTab === 'env' ? 'active' : ''}`}>
            <FileText size={16} /> .env
          </button>
          <button onClick={() => setActiveTab('workflow')} className={`tab-btn ${activeTab === 'workflow' ? 'active' : ''}`}>
            <Github size={16} /> stream.yml
          </button>
        </div>

        <div className="flex-1 p-0 overflow-auto bg-[#1e1e1e]">
          {activeTab === 'setup' && (
             <div className="p-6">
                <div className="mb-4 text-sm text-gray-400">
                   Run this in Termux. It installs dependencies, creates the <code>.env</code> file, and starts services.
                </div>
                <CodeBlock code={setupCode} language="bash" filename="setup.sh" title="One-Click Installer" />
             </div>
          )}
          {activeTab === 'bot' && (
             <div className="p-6">
                <div className="mb-4 text-sm text-gray-400">
                   Main logic. Browses Alist files and triggers GitHub Actions.
                </div>
                <CodeBlock code={botCode} language="python" filename="bot.py" />
             </div>
          )}
          {activeTab === 'env' && (
             <div className="p-6">
                <div className="mb-4 text-sm text-gray-400">
                   <b>Variables File:</b> This file is automatically created by <code>setup.sh</code>, but you can copy this manually if needed.
                </div>
                <CodeBlock code={envCode} language="bash" filename=".env" />
             </div>
          )}
          {activeTab === 'workflow' && (
             <div className="p-6">
                <div className="mb-4 text-sm text-gray-400">
                   Upload to <code>.github/workflows/stream.yml</code> in your repo.
                </div>
                <CodeBlock code={workflowCode} language="yaml" filename="stream.yml" />
             </div>
          )}
        </div>
      </div>

      <style>{`
        .input-field {
          width: 100%;
          background: #111827;
          border: 1px solid #374151;
          color: white;
          padding: 8px;
          border-radius: 4px;
          font-size: 13px;
        }
        .input-field:focus {
          border-color: #3b82f6;
          outline: none;
        }
        .tab-btn {
          flex: 1;
          padding: 16px;
          font-size: 14px;
          font-weight: 500;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          color: #9ca3af;
          transition: all 0.2s;
        }
        .tab-btn:hover { color: white; background: rgba(255,255,255,0.05); }
        .tab-btn.active {
          background: #1f2937;
          color: #3b82f6;
          border-top: 2px solid #3b82f6;
        }
      `}</style>
    </div>
  );
};
