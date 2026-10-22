import type { CapacitorConfig } from "@capacitor/cli";

// Android + iOS apps wrap the same React UI. Change appId to your own reverse-domain id BEFORE the first
// store upload (it can never change afterwards), e.g. "com.yourcompany.jobhunter".
const config: CapacitorConfig = {
  appId: "com.example.aijobhunter",
  appName: "AI Job Hunter",
  webDir: "dist",
  backgroundColor: "#0f1b2d",
  android: { allowMixedContent: false },
  ios: { contentInset: "automatic", backgroundColor: "#0f1b2d" },
  plugins: {
    SplashScreen: { launchShowDuration: 800, backgroundColor: "#0f1b2d", showSpinner: false },
    LocalNotifications: { iconColor: "#0b7a5c" },
  },
};

export default config;
