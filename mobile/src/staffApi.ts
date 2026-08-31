import { apiRequest } from './api';

export type StaffOperation = {
  id: number;
  status: string;
  operation_type: string;
  seller: string;
  buyer: string;
  amount: string;
  players: string[];
  rows: number[];
};

export type StaffClause = {
  id: number;
  player: string;
  seller_club: string;
  buyer_club: string;
  buyer_username: string;
  amount: number;
  status: string;
  requested_at: string;
};

export type StaffReversible = {
  id: number;
  operation_type: string;
  seller: string;
  buyer: string;
  amount: string;
  players: string[];
};

export async function fetchStaffOperations(): Promise<StaffOperation[]> {
  const result = await apiRequest<{ items: StaffOperation[] }>('/api/v1/admin/operations');
  return result.items;
}

export function staffOperationAction(id: number, action: 'approve' | 'reject' | 'pes') {
  return apiRequest<{ ok: boolean }>(`/api/v1/admin/operations/${id}/${action}`, {
    method: 'POST',
    body: '{}',
  });
}

export async function fetchStaffClauses(): Promise<StaffClause[]> {
  const result = await apiRequest<{ items: StaffClause[] }>('/api/v1/admin/clauses');
  return result.items;
}

export function staffClauseAction(id: number, action: 'approve' | 'reject') {
  return apiRequest<{ ok: boolean; transfer_id?: number }>(`/api/v1/admin/clauses/${id}/${action}`, {
    method: 'POST',
    body: '{}',
  });
}

export async function fetchStaffReversible(): Promise<StaffReversible[]> {
  const result = await apiRequest<{ items: StaffReversible[] }>('/api/v1/admin/reversible');
  return result.items;
}

export function undoStaffTransfer(id: number) {
  return apiRequest<{ ok: boolean; reverted: number }>(`/api/v1/admin/reversible/${id}/undo`, {
    method: 'POST',
    body: '{}',
  });
}
