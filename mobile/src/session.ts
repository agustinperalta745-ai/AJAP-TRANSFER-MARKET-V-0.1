import * as SecureStore from 'expo-secure-store';

const KEY = 'ajpa.mobile.session.v1';

export async function loadStoredSession(): Promise<string | null> {
  try { return await SecureStore.getItemAsync(KEY); } catch { return null; }
}

export async function saveStoredSession(token: string): Promise<void> {
  await SecureStore.setItemAsync(KEY, token);
}

export async function clearStoredSession(): Promise<void> {
  try { await SecureStore.deleteItemAsync(KEY); } catch {}
}
