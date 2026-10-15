# WealthVault for Android (native)

A native Android app (Kotlin, Jetpack Compose) for WealthVault. It talks to the same server as the web
app, so every number comes from your brokers and the Azure tables. It uses the web app's design tokens
(`web/src/index.css`) one to one, in light and dark.

Tabs: Overview (value, gain, today, value over time, asset mix against your targets, movers, signals summary,
risk), Holdings (search, filter, sort; a stock opens its Momentum page), Signals (momentum, Swing V2.1 and ATH
breakout on each stock you hold, India and US, buy and sell calls), Stage 2 (the Chartink list with the same
signals and calls) and More: Momentum, Strategies (Swing V2.1 and ATH breakout backtests), Brokers (sync, log
in, add with API keys, remove) and Settings (theme, sign out). Momentum and Strategies need today's Kite login;
the app shows the login link when it is missing.

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
