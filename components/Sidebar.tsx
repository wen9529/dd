import React from 'react';
import { AppView } from '../types';
import { CpuIcon, TerminalIcon, BookIcon, SettingsIcon } from './Icons';

interface SidebarProps {
  currentView: AppView;
  onChangeView: (view: AppView) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentView, onChangeView }) => {
  const menuItems = [
    { id: AppView.DASHBOARD, label: '仪表盘', icon: CpuIcon },
    { id: AppView.GENERATOR, label: '机器人生成器', icon: TerminalIcon },
    { id: AppView.TERMINAL_GUIDE, label: 'Termux 助手', icon: BookIcon },
    { id: AppView.SETTINGS, label: '全局配置', icon: SettingsIcon },
  ];

  return (
    <div className="w-64 bg-black border-r border-gray-900 flex flex-col h-full">
      <div className="p-6 border-b border-gray-900">
        <h1 className="text-xl font-bold text-white tracking-wider flex items-center gap-2">
          <span className="text-termux-accent">./</span>Termux_工坊
        </h1>
        <p className="text-xs text-gray-600 mt-1 font-mono">TERMUX_EDITION_V1.0</p>
      </div>

      <nav className="flex-1 p-4 space-y-2">
        {menuItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onChangeView(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all ${
              currentView === item.id
                ? 'bg-termux-accent text-black shadow-lg shadow-termux-accent/20'
                : 'text-gray-400 hover:bg-gray-900 hover:text-white'
            }`}
          >
            <item.icon className="w-5 h-5" />
            {item.label}
          </button>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-900">
         <div className="bg-[#111] p-3 rounded border border-gray-800">
             <div className="flex items-center gap-2 mb-2">
                 <div className="w-2 h-2 rounded-full bg-termux-accent animate-pulse"></div>
                 <span className="text-xs text-gray-400 font-mono">系统在线</span>
             </div>
             <p className="text-[10px] text-gray-600">
                 Gemini 3 Pro 已激活<br/>
                 准备进行代码合成
             </p>
         </div>
      </div>
    </div>
  );
};