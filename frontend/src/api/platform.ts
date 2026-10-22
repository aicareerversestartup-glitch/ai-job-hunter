// Runs the same UI on the website and inside the Android/iOS apps (Capacitor).
// Web: same-origin API, httpOnly session cookie. Native: API on PUBLIC_URL, bearer token kept in
// the device's app storage (Capacitor Preferences).
import { Capacitor } from "@capacitor/core";

export const isNative = (): boolean => Capacitor.isNativePlatform();
export const platform = (): string => Capacitor.getPlatform(); // "web" | "ios" | "android"

const API_BASE: string = isNative() ? (import.meta.env.VITE_API_BASE as string | undefined ?? "") : "";
export const apiUrl = (path: string) => `${API_BASE}${path}`;

let token: string | null = null;
const TOKEN_KEY = "aijh_token";

export async function loadToken(): Promise<void> {
  if (!isNative()) return;
  const { Preferences } = await import("@capacitor/preferences");
  token = (await Preferences.get({ key: TOKEN_KEY })).value;
}

export async function saveToken(value: string | null): Promise<void> {
  token = value;
  if (!isNative()) return;
  const { Preferences } = await import("@capacitor/preferences");
  if (value) await Preferences.set({ key: TOKEN_KEY, value });
  else await Preferences.remove({ key: TOKEN_KEY });
}

export function authHeaders(): Record<string, string> {
  return isNative() && token ? { Authorization: `Bearer ${token}` } : {};
}

/** Open a job posting or application page: in-app browser on phones, new tab on the web. */
export async function openExternal(url: string): Promise<void> {
  if (!url) return;
  if (isNative()) {
    const { Browser } = await import("@capacitor/browser");
    await Browser.open({ url, presentationStyle: "popover" });
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

async function fetchBlob(path: string): Promise<Blob> {
  const res = await fetch(apiUrl(path), { headers: authHeaders(), credentials: "include" });
  if (!res.ok) throw new Error(`Download failed (${res.status}).`);
  return res.blob();
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

/** Download a CV / letter. On phones it opens the share sheet so it can be saved, mailed or attached. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const blob = await fetchBlob(path);
  if (isNative()) {
    const [{ Filesystem, Directory }, { Share }] = await Promise.all([
      import("@capacitor/filesystem"), import("@capacitor/share"),
    ]);
    const written = await Filesystem.writeFile({ path: filename, data: await blobToBase64(blob), directory: Directory.Cache });
    await Share.share({ title: filename, files: [written.uri], dialogTitle: "Save or send" });
    return;
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Share plain text (e.g. a follow-up email or an answer) using the native share sheet when available. */
export async function shareText(title: string, text: string): Promise<"shared" | "copied"> {
  if (isNative()) {
    const { Share } = await import("@capacitor/share");
    await Share.share({ title, text });
    return "shared";
  }
  await navigator.clipboard?.writeText(text);
  return "copied";
}

export async function imageObjectUrl(path: string): Promise<string> {
  return URL.createObjectURL(await fetchBlob(path));
}

/** A local reminder on the phone, e.g. "Follow up with DHL" in 7 days. Web: no-op. */
export async function scheduleReminder(id: number, title: string, body: string, at: Date): Promise<boolean> {
  if (!isNative()) return false;
  const { LocalNotifications } = await import("@capacitor/local-notifications");
  const perm = await LocalNotifications.requestPermissions();
  if (perm.display !== "granted") return false;
  await LocalNotifications.schedule({ notifications: [{ id, title, body, schedule: { at } }] });
  return true;
}
