# Deploying WealthVault to Azure App Service (Linux)

Local development is unchanged: every deployment setting below defaults to the local behaviour.

## 1. Create the Azure resources (Azure CLI)

```bash
az login
RG=wealthvault-rg; LOC=centralindia; PLAN=wealthvault-plan; APP=<globally-unique-app-name>

az group create -n $RG -l $LOC
az appservice plan create -g $RG -n $PLAN --is-linux --sku B1
az webapp create -g $RG -p $PLAN -n $APP --runtime "PYTHON:3.11"
```

Reuse the storage account you already use locally (Tables and Blobs), or create one:
`az storage account create -g $RG -n <storageaccount> -l $LOC --sku Standard_LRS`. Copy its connection string.

## 2. Configure the app

```bash
az webapp config set -g $RG -n $APP --always-on true --startup-file "bash startup.sh" --http20-enabled true
az webapp update   -g $RG -n $APP --https-only true
az webapp config appsettings set -g $RG -n $APP --settings \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true \
  WEBSITES_ENABLE_APP_SERVICE_STORAGE=true \
  ENVIRONMENT=production \
  DATA_DIR=/home/data \
  PUBLIC_BASE_URL=https://$APP.azurewebsites.net \
  AZURE_STORAGE_CONNECTION_STRING="<connection string>" \
  GOOGLE_CLIENT_ID="<id>.apps.googleusercontent.com" \
  JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  CREDENTIAL_ENCRYPTION_KEY="<your existing key>" \
  INDMONEY_CLIENT_ID="<id>" INDMONEY_CLIENT_SECRET="<secret>" \
  ALLOWED_ORIGINS='["https://'$APP'.azurewebsites.net"]'
```

Notes
- Keep exactly **one instance** (do not scale out or enable autoscale): refresh jobs, broker sessions and the INDmoney login state are held in memory.
- `CREDENTIAL_ENCRYPTION_KEY` must be the **same key** you use locally, or the stored Groww and Angel One credentials cannot be decrypted. Keep a backup.
- The app refuses to start in production with the default `JWT_SECRET`, a missing encryption key or Google client id, or `ALLOWED_ORIGINS` of `*`.
- Use a custom domain? Put it in both `PUBLIC_BASE_URL` and `ALLOWED_ORIGINS`.

## 3. Google Cloud console
APIs & Services, Credentials, your OAuth 2.0 Web client: add `https://<APP>.azurewebsites.net` under **Authorized JavaScript origins**. No redirect URI is needed (Google Sign-In uses an ID token). If the consent screen is in Testing, add your account as a test user.

## 4. INDmoney
Register `https://<APP>.azurewebsites.net/api/v1/portfolio/oauth/indmoney/callback` as a redirect URI for your INDmoney MCP client, then connect from the Brokers page after deploying. Confirm INDmoney accepts a non-localhost redirect.

## 5. Angel One (only if you use it)
SmartAPI needs a fixed public IP registered with Angel One. App Service outbound IPs are shared. Either put the app behind a VNet with a NAT gateway and a static public IP, or use a plan whose outbound IPs you whitelist. Then set `ANGELONE_PUBLIC_IP=<that ip>`.

## 6. Deploy from GitHub
1. Enable publish credentials: Portal, your app, Configuration, General settings, **SCM Basic Auth Publishing Credentials = On**.
2. Download the publish profile: Portal, your app, Overview, **Download publish profile**.
3. In GitHub, repo Settings, Secrets and variables, Actions:
   - Secret `AZURE_WEBAPP_PUBLISH_PROFILE`: the whole XML file contents.
   - Variable `AZURE_WEBAPP_NAME`: your app name.
4. Actions tab, **Deploy to Azure App Service**, Run workflow. It runs the tests, builds the frontend into `dist/`, zips and deploys. Azure then installs `requirements.txt`.

## 7. Verify
- `https://<APP>.azurewebsites.net/health` returns ok.
- Open the site, sign in with Google.
- Brokers page: connect Kite (daily login) and INDmoney; check Holdings.
- Logs: `az webapp log tail -g $RG -n $APP`.

## Rollback
Re-run the workflow on an older commit (Run workflow, choose the branch or tag), or use Deployment Center to redeploy a previous build.

## Android app

See `ANDROID.md`. Extra optional app settings: `SUPPORT_EMAIL`, `ANDROID_PACKAGE_NAME`, `ANDROID_SHA256_FINGERPRINTS`.
