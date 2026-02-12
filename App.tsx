import React from 'react';
import { TermuxGuide } from './components/TermuxGuide';
import { FileCode, Terminal } from 'lucide-react';

const App: React.FC = () => {
  return (
    <div className="flex flex-col h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="h-16 border-b border-gray-800 bg-gray-900 flex items-center justify-between px-6 flex-shrink-0 z-10">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600 p-2 rounded-lg">
            <Terminal className="text-white h-5 w-5" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-white">
            StreamForge <span className="text-gray-500 font-normal">| Deployment Kit</span>
          </h1>
        </div>
        <div className="flex gap-4 text-xs font-mono text-gray-500">
          <span className="flex items-center gap-1"><FileCode size={12}/> setup.sh</span>
          <span className="flex items-center gap-1"><FileCode size={12}/> bot.py</span>
          <span className="flex items-center gap-1"><FileCode size={12}/> stream.yml</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto bg-gray-900 relative">
        <TermuxGuide />
      </main>
    </div>
  );
};

export default App;
