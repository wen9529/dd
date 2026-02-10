import React, { useState, useEffect } from 'react';
import { SettingsIcon } from './Icons';

export const Settings: React.FC = () => {
  const [token, setToken] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    // 从 localStorage 加载设置
    const storedToken = localStorage.getItem('bot_token');
    const storedOwnerId = localStorage.getItem('bot_owner_id');
    if (storedToken) setToken(storedToken);
    if (storedOwnerId) setOwnerId(storedOwnerId);
  }, []);

  const handleSave = () => {
    localStorage.setItem('bot_token', token);
    localStorage.setItem('bot_owner_id', ownerId);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex flex-col h-full bg-[#111] p-8 text-white">
      <h2 className="text-3xl font-bold mb-8 flex items-center gap-3">
        <SettingsIcon className="w-8 h-8 text-termux-accent" />
        全局配置
      </h2>

      <div className="bg-[#1e1e1e] border border-gray-800 rounded-xl p-6 max-w-2xl">
        <p className="text-gray-400 mb-6 text-sm">
          在此处配置的 Token 和 ID 将会被 AI 自动注入到生成的 Python 代码中。
          这些信息仅保存在你的浏览器本地存储中，不会上传到服务器。
        </p>

        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Telegram Bot Token
            </label>
            <input
              type="text"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="例如: 123456789:ABCdef..."
              className="w-full bg-[#111] border border-gray-700 rounded-lg p-3 text-white focus:border-termux-accent focus:outline-none font-mono text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Owner ID (你的用户 ID)
            </label>
            <input
              type="text"
              value={ownerId}
              onChange={(e) => setOwnerId(e.target.value)}
              placeholder="例如: 1878794912"
              className="w-full bg-[#111] border border-gray-700 rounded-lg p-3 text-white focus:border-termux-accent focus:outline-none font-mono text-sm"
            />
          </div>

          <div className="pt-4">
            <button
              onClick={handleSave}
              className="bg-termux-accent text-black px-6 py-2 rounded-lg font-bold hover:bg-emerald-400 transition-colors w-full sm:w-auto"
            >
              {saved ? '已保存！' : '保存配置'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};