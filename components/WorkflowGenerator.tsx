import React, { useState } from 'react';
import { StreamConfig } from '../types';
import { DEFAULT_STREAM_CONFIG, GITHUB_WORKFLOW_TEMPLATE } from '../constants';
import { CodeBlock } from './CodeBlock';
import { Github, Play, Settings, ExternalLink } from 'lucide-react';

export const WorkflowGenerator: React.FC = () => {
  const [config, setConfig] = useState<StreamConfig>(DEFAULT_STREAM_CONFIG);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setConfig(prev => ({ ...prev, [name]: value }));
  };

  const workflowCode = GITHUB_WORKFLOW_TEMPLATE(config);

  return (
    <div className="max-w-6xl mx-auto p-6 h-full flex flex-col md:flex-row gap-6 animate-fade-in">
      {/* Configuration Form */}
      <div className="w-full md:w-1/3 bg-gray-800 p-6 rounded-xl border border-gray-700 overflow-y-auto">
        <div className="flex items-center gap-2 mb-6 text-primary-500">
          <Settings size={24} />
          <h2 className="text-xl font-bold text-white">Stream Config</h2>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Source File URL (from Alist)</label>
            <input
              type="text"
              name="fileUrl"
              value={config.fileUrl}
              onChange={handleChange}
              placeholder="http://ip:port/d/drive/video.mp4"
              className="w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-primary-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Telegram RTMP URL</label>
            <input
              type="text"
              name="telegramRtmpUrl"
              value={config.telegramRtmpUrl}
              onChange={handleChange}
              className="w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-primary-500 transition-colors"
            />
            <p className="text-xs text-gray-500 mt-1">Found in Telegram Channel &gt; Start Stream &gt; Streaming with other apps.</p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">GitHub Secret Name (Optional)</label>
            <div className="text-xs text-gray-500 mb-2">
              For security, add your Stream Key as a secret named <code>TELEGRAM_STREAM_KEY</code> in GitHub repository settings.
            </div>
          </div>
        </div>

        <div className="mt-8 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
          <h4 className="text-yellow-400 font-bold text-sm mb-2 flex items-center gap-2">
            <ExternalLink size={14} /> Usage
          </h4>
          <ol className="list-decimal list-inside text-xs text-gray-300 space-y-1">
            <li>Create a file <code>.github/workflows/stream.yml</code></li>
            <li>Paste the generated code</li>
            <li>Go to "Actions" tab in GitHub</li>
            <li>Select "Stream to Telegram"</li>
            <li>Click "Run workflow"</li>
          </ol>
        </div>
      </div>

      {/* Code Output */}
      <div className="w-full md:w-2/3 flex flex-col">
        <div className="flex items-center gap-2 mb-4">
          <Github className="text-white" />
          <h2 className="text-xl font-bold">Generated Workflow (.yml)</h2>
          <span className="ml-auto text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded">
             {config.telegramRtmpUrl ? 'Ready to Deploy' : 'Missing Config'}
          </span>
        </div>
        
        <div className="flex-1 overflow-auto">
           <CodeBlock code={workflowCode} language="yaml" title=".github/workflows/stream.yml" />
        </div>
      </div>
    </div>
  );
};
