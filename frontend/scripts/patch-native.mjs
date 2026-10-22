// Run after `npx cap add android` / `npx cap add ios` (and again after `npx cap sync` if you like; it is idempotent).
// Adds what the stores and the AdMob SDK require:
//  - AdMob application IDs (from .env.app: ADMOB_APP_ID_ANDROID / ADMOB_APP_ID_IOS; Google's test IDs otherwise)
//  - iOS privacy strings (tracking, photo library, camera) and the export-compliance flag
// Usage: node scripts/patch-native.mjs
import fs from "node:fs";

const env = Object.fromEntries((fs.existsSync(".env.app") ? fs.readFileSync(".env.app", "utf8") : "")
  .split(/\r?\n/).filter((l) => l && !l.startsWith("#") && l.includes("="))
  .map((l) => [l.slice(0, l.indexOf("=")).trim(), l.slice(l.indexOf("=") + 1).trim()]));
const ANDROID_ID = env.ADMOB_APP_ID_ANDROID || "ca-app-pub-3940256099942544~3347511713"; // Google test app id
const IOS_ID = env.ADMOB_APP_ID_IOS || "ca-app-pub-3940256099942544~1458002511";

const manifest = "android/app/src/main/AndroidManifest.xml";
if (fs.existsSync(manifest)) {
  let xml = fs.readFileSync(manifest, "utf8");
  if (!xml.includes("com.google.android.gms.ads.APPLICATION_ID")) {
    xml = xml.replace(/<application([^>]*)>/, `<application$1>\n        <meta-data android:name="com.google.android.gms.ads.APPLICATION_ID" android:value="${ANDROID_ID}"/>`);
  } else {
    xml = xml.replace(/(com\.google\.android\.gms\.ads\.APPLICATION_ID"\s+android:value=")[^"]*/, `$1${ANDROID_ID}`);
  }
  if (!xml.includes("com.google.android.gms.permission.AD_ID")) {
    xml = xml.replace(/<\/manifest>/, `    <uses-permission android:name="com.google.android.gms.permission.AD_ID"/>\n</manifest>`);
  }
  fs.writeFileSync(manifest, xml);
  console.log("Android: AdMob app id set.");
}

const plist = "ios/App/App/Info.plist";
if (fs.existsSync(plist)) {
  let p = fs.readFileSync(plist, "utf8");
  const set = (key, value) => {
    const re = new RegExp(`<key>${key}</key>\\s*<[^>]+>[^<]*</[^>]+>`);
    const entry = `<key>${key}</key>\n\t<${value.tag}>${value.text}</${value.tag}>`;
    p = re.test(p) ? p.replace(re, entry) : p.replace(/<dict>/, `<dict>\n\t${entry}`);
  };
  set("GADApplicationIdentifier", { tag: "string", text: IOS_ID });
  set("NSUserTrackingUsageDescription", { tag: "string", text: "Allows more relevant ads in the free version. Your CV and applications are never used for ads." });
  set("NSPhotoLibraryUsageDescription", { tag: "string", text: "Choose a CV file or profile photo to upload." });
  set("NSCameraUsageDescription", { tag: "string", text: "Take a profile photo for CV formats that use one." });
  if (!p.includes("ITSAppUsesNonExemptEncryption")) {
    p = p.replace(/<dict>/, "<dict>\n\t<key>ITSAppUsesNonExemptEncryption</key>\n\t<false/>");
  }
  if (!p.includes("SKAdNetworkItems")) {
    p = p.replace(/<dict>/, "<dict>\n\t<key>SKAdNetworkItems</key>\n\t<array>\n\t\t<dict>\n\t\t\t<key>SKAdNetworkIdentifier</key>\n\t\t\t<string>cstr6suwn9.skadnetwork</string>\n\t\t</dict>\n\t</array>");
  }
  fs.writeFileSync(plist, p);
  console.log("iOS: AdMob id, privacy strings and export compliance set.");
}
