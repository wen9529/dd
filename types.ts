
export interface StreamConfig {
  // GitHub Repo Details
  githubUser: string;
  githubRepo: string;
  githubPat: string; // Personal Access Token
  
  // Telegram Configuration
  telegramBotToken: string;
  telegramAdminId: string;
  telegramRtmpUrl: string;
  telegramStreamKey: string;

  // Alist Configuration
  alistPassword: string;
  aria2Secret: string; // New: For offline download security

  // File Defaults
  fileName: string;
  fileUrl: string;

  // Stream Settings
  defaultCoverUrl: string; // Custom cover for audio files
  videoBitrate: string;    // e.g., "6000k"
}

export interface Message {
  id: string;
  role: 'user' | 'model';
  content: string;
  timestamp: number;
}