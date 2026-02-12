import React, { useState } from 'react';
import { Clipboard, Check, Download } from 'lucide-react';

interface CodeBlockProps {
  code: string;
  language?: string;
  title?: string;
  filename?: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ code, language = 'bash', title, filename }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!filename) return;
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700 my-4 shadow-lg">
      <div className="flex justify-between items-center px-4 py-2 bg-gray-700/50 border-b border-gray-700">
        <span className="text-xs font-mono text-gray-300 uppercase">{title || language}</span>
        <div className="flex gap-2">
          {filename && (
            <button
              onClick={handleDownload}
              className="p-1 text-gray-400 hover:text-blue-400 transition-colors"
              title={`Download ${filename}`}
            >
              <Download size={16} />
            </button>
          )}
          <button
            onClick={handleCopy}
            className="p-1 text-gray-400 hover:text-white transition-colors"
            title="Copy code"
          >
            {copied ? <Check size={16} className="text-green-400" /> : <Clipboard size={16} />}
          </button>
        </div>
      </div>
      <div className="p-4 overflow-x-auto">
        <pre className="font-mono text-sm text-gray-200 whitespace-pre">
          {code}
        </pre>
      </div>
    </div>
  );
};