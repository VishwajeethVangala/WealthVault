# WealthVault for Android (native)

A native Android app (Kotlin, Jetpack Compose) for WealthVault. It talks to the same server as the web
app, so every number comes from your brokers and the Azure tables. It uses the web app's design tokens
(`web/src/index.css`) one to one, in light and dark.

Tabs: Overview (value, gain, today, value over time, asset mix against your targets, movers, signals summary,
watchlist radar, risk), Holdings (search, filter, sort, with top segmented toggle for Holdings vs. Watchlist; a stock opens its Momentum page), Watchlist & Pre-Flight Radar (tracked prospect stocks, trend score verdict, ATH breakout status, quick add search with Zerodha Kite autocomplete, momentum & strategy links), Signals (momentum and ATH
breakout on each stock you hold, India and US, buy and sell calls, amber Watchlist filter and badges), Stage 2 (the Chartink list with the same
signals and calls) and More: Momentum, the ATH Strategy (breakout backtest), Brokers (sync, log
in, add with API keys, remove) and Settings (theme, sign out). Momentum and Strategies need today's Kite login;
the app shows the login link when it is missing.

## Build and Test

Tools live outside the repo in `D:\Gravity\android-tools` (portable JDK 17, Android SDK 35, Gradle 8.11.1).

### In PowerShell:
```powershell
$env:JAVA_HOME = "D:\Gravity\android-tools\jdk-17.0.20.1+1"
$env:GRADLE_USER_HOME = "D:\Gravity\android-tools\gradle-home"
cd android

# Run unit tests
.\gradlew.bat testDebugUnitTest

# Assemble debug APK
.\gradlew.bat assembleDebug
```

### In Command Prompt (cmd.exe):
```cmd
set JAVA_HOME=D:\Gravity\android-tools\jdk-17.0.20.1+1
set GRADLE_USER_HOME=D:\Gravity\android-tools\gradle-home
cd android
gradlew.bat testDebugUnitTest
gradlew.bat assembleDebug
```

The APK lands in `app/build/outputs/apk/debug/app-debug.apk`. Copy it to the phone and open it to install
(allow "install unknown apps" once). `local.properties` (not committed) points at the SDK.

The server address is built in from `wvBaseUrl` in `gradle.properties` (the Azure portal), so nobody types
it. Override with `-PwvBaseUrl=https://...`; an empty value brings back an address field on the sign-in screen.

## One-time Google sign-in setup (needed before sign-in works)

Google only signs in an Android app it knows. In Google Cloud Console, in the same project as the web
client ID the server uses (`GOOGLE_CLIENT_ID`):

1. APIs & Services, Credentials, Create credentials, OAuth client ID, type **Android**.
2. Package name: `com.vangala.wealthvault` (the name registered on Google Play).
3. SHA-1: run `gradlew.bat signingReport` and copy the SHA-1 of the `debug` variant (and later the release key's).

Nothing changes on the server: the app asks Google for an ID token for the web client ID (read from
`/api/v1/auth/config`) and sends it to `/api/v1/auth/google`, exactly as the web app does.

## Release build and Play Store

Run `powershell -ExecutionPolicy Bypass -File scriptsuild_all.ps1` from the repo root. It builds the web zip for
Azure and the signed Android app, checks the app carries the key Google Play expects, and leaves three files in
`D:\Gravity`: `wealthvault-release.zip`, `WealthVault-<version>-release.aab` (Play) and `...-release.apk`.
Use `-SkipWeb`, `-SkipAndroid` or `-SkipTests` to do part of it.

Signing: Google Play registered the upload key made with the first (PWA) upload on 14 Oct 2026, SHA-1
`22:CE:1D:79:AB:74:38:66:07:27:B9:4B:36:F5:A9:66:7A:E4:4B:EF`. The app is signed with that key, kept at
`D:\Gravityndroid-tools\keys\wealthvault-play-upload.keystore` (password in `wealthvault-play-upload-info.txt`
beside it); `android/keystore.properties` (not committed) points at it. **Back up the whole `keys` folder somewhere
safe: without that key the app cannot be updated on Play.** A second key made earlier (`wealthvault-upload.jks`,
SHA-1 `10:F1:...:DE:C2`) was rejected by Play and is not used.

Each release needs a higher `versionCode` in `app/build.gradle.kts`. For Google sign-in an Android OAuth client is
needed per signing key: debug (testing), the key above (a release APK installed directly) and the key Play App
Signing uses (Play Console, App integrity). Play links: `<server>/privacy` and `<server>/delete-account`.
`gradlew.bat assembleReleaseCheck` makes a debuggable copy of the shrunk build for emulator tests.

## Tested

On an Android 15 emulator (Pixel 7 size) against a local server with real data, light and dark: every tab,
Signals and Stage 2 calls, broker set-up dialogs (opened and cancelled), targets, chart readout and
scrolling, sign out. Momentum and Strategies were also checked with results from the server's own analytics
code on generated prices, since Kite was not logged in. No app crashes. A cold start took 1.3 to 2 seconds on
the emulator once it had memory to spare (not measured on a real phone yet).

Note: this app and the PWA wrapper on the `android-pwa` branch use the same package name, so only one of
them can be on a phone (or in Play) at a time.

## Not yet in the app

The Swing setups, backtest and journal live on the `SwingTrade` branch of the web app, not on `main`, so they
are not in the app. Strategy settings (years, UT Bot key, stop multiple) use the web app's defaults.
