export enum AppView {
  DASHBOARD = 'DASHBOARD',
  GENERATOR = 'GENERATOR',
  TERMINAL_GUIDE = 'TERMINAL_GUIDE',
  SETTINGS = 'SETTINGS'
}

export interface BotProject {
  id: string;
  name: string;
  description: string;
  code: string;
  dependencies: string[];
  createdAt: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  codeBlock?: string;
  isThinking?: boolean;
}
