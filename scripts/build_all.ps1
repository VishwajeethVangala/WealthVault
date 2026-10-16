<#
  Build everything you upload, in one go.

    powershell -ExecutionPolicy Bypass -File scripts\build_all.ps1

  Makes, in D:\Gravity:
    wealthvault-release.zip          the web app + server, for Azure (manual upload)
    WealthVault-<version>-release.aab   the Android app bundle, for Google Play
    WealthVault-<version>-release.apk   the same app as an APK, to install directly on a phone

  Options:
    -SkipWeb       only the Android app
    -SkipAndroid   only the web zip
    -SkipTests     do not run the Python tests before zipping the web app
    -OutDir <dir>  put the files somewhere else (default D:\Gravity)

  Needs (already set up on this PC): Python, Node, the Android tools in D:\Gravity\android-tools, and the Play
  upload key listed in android\keystore.properties. The script checks the app is signed with the key Google Play
  expects (SHA-1 22:CE:1D:79:...:E4:4B:EF) and stops if not.
#>
param(
    [switch]$SkipWeb,
    [switch]$SkipAndroid,
    [switch]$SkipTests,
    [string]$OutDir = "D:\Gravity"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Tools = "D:\Gravity\android-tools"
$PlayKeySha1 = "22:CE:1D:79:AB:74:38:66:07:27:B9:4B:36:F5:A9:66:7A:E4:4B:EF"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$results = @()

function Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }

# ---------------------------------------------------------------- web + server zip
if (-not $SkipWeb) {
    Step "Web app: tests, build, zip"
    $args = @("scripts\build_release_zip.py", "--out", (Join-Path $OutDir "wealthvault-release.zip"))
    if ($SkipTests) { $args += "--skip-tests" }
    Push-Location $Repo
    try {
        & python @args
        if ($LASTEXITCODE -ne 0) { throw "The web build failed (see above). Nothing was uploaded or changed." }
    } finally { Pop-Location }
    $results += (Join-Path $OutDir "wealthvault-release.zip")
}

# ---------------------------------------------------------------- Android app
if (-not $SkipAndroid) {
    Step "Android app: signed release bundle and APK (takes about 5 minutes)"
    $android = Join-Path $Repo "android"
    if (-not (Test-Path (Join-Path $android "keystore.properties"))) {
        throw "android\keystore.properties is missing, so the app would not be signed with the Play upload key."
    }
    $env:JAVA_HOME = Join-Path $Tools "jdk-17.0.20.1+1"
    $env:GRADLE_USER_HOME = Join-Path $Tools "gradle-home"

    Push-Location $android
    try {
        & .\gradlew.bat bundleRelease assembleRelease --console=plain
        if ($LASTEXITCODE -ne 0) { throw "The Android build failed (see above)." }
    } finally {
        & .\gradlew.bat --stop | Out-Null   # free the memory the build tools hold
        Pop-Location
    }

    $aab = Join-Path $android "app\build\outputs\bundle\release\app-release.aab"
    $apk = Join-Path $android "app\build\outputs\apk\release\app-release.apk"

    # which key signed it? Google Play only accepts the key it registered.
    $keytool = Join-Path $env:JAVA_HOME "bin\keytool.exe"
    $cert = & $keytool -printcert -jarfile $aab 2>&1 | Select-String "SHA1:"
    $sha1 = ($cert -replace ".*SHA1:\s*", "").ToString().Trim()
    if ($sha1 -ne $PlayKeySha1) {
        throw "The app bundle is signed with $sha1, but Google Play expects $PlayKeySha1. Check android\keystore.properties."
    }
    Write-Host "Signed with the Google Play upload key ($sha1)" -ForegroundColor Green

    # the version, from the build file
    $ver = (Select-String -Path (Join-Path $android "app\build.gradle.kts") -Pattern 'versionName\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
    $aabOut = Join-Path $OutDir "WealthVault-$ver-release.aab"
    $apkOut = Join-Path $OutDir "WealthVault-$ver-release.apk"
    Copy-Item $aab $aabOut -Force
    Copy-Item $apk $apkOut -Force
    $results += $aabOut, $apkOut
}

Step "Done"
foreach ($f in $results) { "{0,-60} {1,8:N1} MB" -f $f, ((Get-Item $f).Length / 1MB) }
Write-Host "`nNext:"
if (-not $SkipWeb) { Write-Host "  Azure : upload wealthvault-release.zip (portal: your app > Deployment Center, or Kudu Zip Push Deploy), then open the site." }
if (-not $SkipAndroid) { Write-Host "  Play  : upload the .aab in Play Console (a new release needs a higher versionCode in android\app\build.gradle.kts)." }
