import React from 'react';

interface TerminalProps {
  lines: string[];
  typing?: boolean;
}

export const Terminal: React.FC<TerminalProps> = ({ lines, typing }) => {
  return (
    <div className="bg-[#121212] rounded-lg border border-gray-800 shadow-2xl overflow-hidden flex flex-col h-full font-mono text-sm">
      <div className="bg-[#1a1a1a] px-4 py-2 flex items-center gap-2 border-b border-gray-800">
        <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
        <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
        <div className="w-3 h-3 rounded-full bg-green-500/80"></div>
        <span className="ml-2 text-xs text-gray-500">termux — bash</span>
      </div>
      <div className="p-4 overflow-y-auto flex-1 text-gray-300 space-y-1">
        <div className="text-gray-500 mb-4">
          Welcome to Termux!<br />
          Wiki: https://wiki.termux.com<br />
          Community: https://termux.com/community<br />
          <br />
          Working with packages:<br />
          &nbsp;* Search:  pkg search &lt;query&gt;<br />
          &nbsp;* Install: pkg install &lt;package&gt;<br />
          &nbsp;* Upgrade: pkg upgrade<br />
        </div>
        
        {lines.map((line, idx) => (
          <div key={idx} className="break-all whitespace-pre-wrap">
            <span className="text-termux-accent mr-2">~ $</span>
            <span>{line}</span>
          </div>
        ))}
        
        {typing && (
           <div className="animate-pulse">
             <span className="text-termux-accent mr-2">~ $</span>
             <span className="inline-block w-2 h-4 bg-termux-accent align-middle"></span>
           </div>
        )}
      </div>
    </div>
  );
};
