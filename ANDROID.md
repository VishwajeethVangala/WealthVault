# Android app (Trusted Web Activity)

The Android app is the website in a full-screen Android shell (Chrome, no address bar). There is no separate Android code to keep in this repo. The site is an installable app (manifest, icons, service worker); PWABuilder packages it into the `.aab` file Google Play takes.

## What the site already provides
- `web/public/manifest.webmanifest`, icons (`icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png`) and `sw.js`.
- `/.well-known/assetlinks.json`, built from app settings (below). It is what lets Android drop the browser bar.
- Public pages Play asks for: `/privacy` and `/delete-account`.
- In-app **Account** page (tap the profile picture) with **Delete my account and data**.

## App settings to add in Azure (Configuration, Application settings)
| Name | Value |
|---|---|
| `ANDROID_PACKAGE_NAME` | `com.wealthvault.app` (must match the package id used in PWABuilder) |
| `ANDROID_SHA256_FINGERPRINTS` | the signing-key fingerprint(s), comma separated (see step 3) |
| `SUPPORT_EMAIL` | the contact address shown on the privacy page |

Open `https://<your-app>/.well-known/assetlinks.json` to check. It shows `[]` until a fingerprint is set.

## Steps
1. Deploy this branch's zip to Azure, restart, and open the site in Chrome on your phone. The menu should offer **Install app**.
2. Set `SUPPORT_EMAIL` (and restart).
3. Go to https://www.pwabuilder.com, enter the site URL, choose **Package for stores, Android**.
   - Package ID `com.wealthvault.app`, name `WealthVault`.
   - Choose **Google Play** signing: let Play manage the key. Download the package.
   - The fingerprint comes from Play Console (Release, Setup, App signing, SHA-256 of the *app signing key*). Add it to `ANDROID_SHA256_FINGERPRINTS`. If you also sideload the upload build, add the *upload key* fingerprint too.
4. Play Console: create the app, then **Testing, Internal testing**, create a release, upload the `.aab`, add testers by email, and share the opt-in link.
5. Declarations Play asks for: privacy policy URL (`/privacy`), account deletion URL (`/delete-account`), Data safety, content rating, financial features (no loans, trading or crypto), and "app access" with test-login notes.
6. Google Cloud, OAuth consent screen: if it says **Testing**, add each friend's Gmail under Test users, or they cannot sign in.

## Keep out of git
The signing keystore and its passwords, and the `.aab` build files.
