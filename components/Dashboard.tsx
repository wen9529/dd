import React from 'react';
import { BotProject } from '../types';
import { TerminalIcon, PlusIcon } from './Icons';

interface DashboardProps {
  projects: BotProject[];
  onCreateNew: () => void;
  onSelectProject: (p: BotProject) => void;
  onDeleteProject: (id: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ projects, onCreateNew, onSelectProject, onDeleteProject }) => {
  return (
    <div className="p-8 h-full overflow-y-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
           <h1 className="text-3xl font-bold text-white mb-2">仪表盘</h1>
           <p className="text-gray-400">管理你的 Termux 机器人项目</p>
        </div>
        <button
          onClick={onCreateNew}
          className="bg-termux-accent text-black px-4 py-2 rounded-md font-bold flex items-center gap-2 hover:bg-emerald-400 transition-colors shadow-[0_0_15px_rgba(0,230,118,0.3)]"
        >
          <PlusIcon className="w-5 h-5" /> 新建机器人
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {projects.map((project) => (
          <div
            key={project.id}
            onClick={() => onSelectProject(project)}
            className="group bg-[#1e1e1e] border border-gray-800 rounded-xl p-6 hover:border-termux-accent transition-all cursor-pointer hover:shadow-lg hover:shadow-termux-accent/5 relative"
          >
            <div className="flex justify-between items-start mb-4">
              <div className="w-10 h-10 rounded-lg bg-[#252525] flex items-center justify-center group-hover:bg-termux-accent/20 transition-colors">
                <TerminalIcon className="w-6 h-6 text-gray-400 group-hover:text-termux-accent" />
              </div>
              <span className="text-xs text-gray-500 font-mono">
                {new Date(project.createdAt).toLocaleDateString()}
              </span>
            </div>
            
            <h3 className="text-xl font-bold text-gray-200 mb-2 truncate pr-6">{project.name}</h3>
            <p className="text-sm text-gray-400 line-clamp-3 mb-4 h-10">
              {project.description}
            </p>
            
            <div className="flex flex-wrap gap-2 mt-auto">
               {project.dependencies.slice(0, 3).map(dep => (
                   <span key={dep} className="px-2 py-1 bg-black/30 text-gray-500 text-[10px] rounded border border-gray-800 font-mono">
                       {dep}
                   </span>
               ))}
               {project.dependencies.length > 3 && (
                   <span className="px-2 py-1 bg-black/30 text-gray-500 text-[10px] rounded border border-gray-800 font-mono">
                       +{project.dependencies.length - 3}
                   </span>
               )}
            </div>

             <button 
                onClick={(e) => { e.stopPropagation(); onDeleteProject(project.id); }}
                className="absolute top-4 right-4 text-gray-600 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
            >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
            </button>
          </div>
        ))}

        {projects.length === 0 && (
          <div className="col-span-full flex flex-col items-center justify-center p-12 border-2 border-dashed border-gray-800 rounded-xl text-gray-500 gap-4">
            <p className="text-lg">暂无机器人。</p>
            <button onClick={onCreateNew} className="text-termux-accent hover:underline">
              创建你的第一个机器人
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
