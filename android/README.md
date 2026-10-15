# WealthVault for Android (native)

A native Android app (Kotlin, Jetpack Compose) for WealthVault. It talks to the same server as the web
app, so every number comes from your brokers and the Azure tables. It uses the web app's design tokens
(`web/src/index.css`) one to one, in light and dark.

Screens: sign in with Google, Overview (value, gain, today, asset mix, movers), Holdings (search, filter by
asset class), Brokers (status, sync, broker login link) and Settings (theme, sign out).

## Build

Tools live outside the repo in `D:\Gravity\android-tools` (portable JDK 17, Android SDK 35, Gradle 8.11.1).

```
cd android
set JAVA_HOME=D:\Gravity\android-tools\jdk-17.0.20.1+1
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

## Tested

On an Android 15 emulator (Pixel 7 size) against a local server with real data: sign in (test token),
Overview, Holdings (search, class chips), Brokers (status, login link, local sync times), Settings (theme,
sign out), light and dark. No crashes. A cold start took about 7 seconds on the
slow software-graphics emulator (not measured on a real phone yet).

Note: this app and the PWA wrapper on the `android-pwa` branch use the same package name, so only one of
them can be on a phone (or in Play) at a time.

## Not yet in the app

Equity signals, Stage 2, Momentum, Strategies and Swing setups are on the web app only for now; adding a
broker connection is also done on the web app.
