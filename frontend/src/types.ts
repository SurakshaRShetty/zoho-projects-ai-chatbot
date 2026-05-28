export interface PendingAction {
  tool: string;
  params: Record<string, unknown>;
  description: string;
}

export interface ChatApiResponse {
  type: 'message' | 'confirmation_required' | 'error';
  content: string;
  pending_action: PendingAction | null;
  session_id: string;
}

export interface UserProfile {
  id: number;
  zoho_user_id: string;
  email: string;
  display_name: string | null;
  portal_id: string | null;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'error';
  content: string;
  pendingAction?: PendingAction;
  timestamp: Date;
}
