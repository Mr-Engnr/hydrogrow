# Deployment

Runbook for provisioning and deploying the full stack on Azure. The original
deployment ran on a subscription that has since been retired; these steps
reproduce it on any subscription.

## Resources

| Resource | Service | Purpose |
|---|---|---|
| Resource group | Resource Group | Groups everything |
| IoT Hub (Free F1) | Azure IoT Hub | Device auth, MQTT ingestion, 8000 msg/day |
| Function App (Consumption) | Azure Functions | Telemetry persistence + analytics API |
| Storage account | Blob Storage | telemetry-data container, one JSON per reading |
| App Service (F1) | Azure Web App | Express backend + compiled React frontend, one URL |

## Provisioning

See `cloud/infra/provision.sh` for the scripted version. Key settings that live
in Azure app settings, never in code:

**Function App:**
- `IotHubConnection` - Event Hub-compatible connection string from IoT Hub built-in endpoints
- `AzureWebJobsStorage` - storage connection string
- `FUNCTIONS_WORKER_RUNTIME=python`, `FUNCTIONS_EXTENSION_VERSION=~4`

**Web App:**
- `PORT=8080` (Azure's fixed internal Node port; anything else crashes on boot)
- `NODE_ENV=production`
- `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CONTAINER_NAME=telemetry-data`
- `AZURE_FUNCTION_URL` - analytics endpoint, proxied by the backend

Set via:
```bash
az webapp config appsettings set --name <app> --resource-group <rg> --settings KEY="VALUE"
```

## Deploying the web app (frontend + backend together)

```powershell
# 1. Build the React app
npm run build

# 2. Replace (never merge) the staged build
Remove-Item -Recurse -Force backend\build
Copy-Item -Recurse -Force build backend\build

# 3. Sanity-check no stale URLs survived in the bundle
Select-String -Recurse -Path backend\build -Pattern "<old-function-app-host>"

# 4. Deploy from inside the backend folder
cd backend
az webapp up --name <app-name> --resource-group <rg> --runtime "NODE:20-lts" --sku F1
```

The `Remove-Item` step is not optional. `Copy-Item -Force` merges into an
existing directory rather than replacing it, which leaves stale JS bundles
being served alongside new ones. This exact failure shipped once.

## Deploying the Function App

```bash
cd cloud/functions
func azure functionapp publish <function-app-name> --python
```

## Pitfalls encountered in the original deployment

| Symptom | Root cause | Fix |
|---|---|---|
| Function runtime Error after deploy | local.settings.json is never deployed; IotHubConnection missing in Azure | Set the app setting via CLI |
| App Service "Application Error" on boot | PORT read from undeployed .env | PORT=8080 app setting |
| Express crash: PathError on wildcard | Express 5 changed wildcard syntax | `app.get('/{*path}')` |
| Root URL shows text instead of React | A GET / route intercepted static serving | Remove the route, fall through to static |
| Analytics empty arrays | Filename date parsing mismatch | Parse first 8 chars of blob name as YYYYMMDD |
| Wrong "latest" blob picked | Non-telemetry file in container sorted first | Regex filter `^\d{8}_\d{6}_\d+\.json$` |

## Known limits

- F1 App Service: 60 CPU minutes/day. Fine for demo traffic; B1 for production.
- Free-tier App Service filesystem is not persistent across deployments. The
  file-backed user store resets on every deploy; a real deployment needs
  Cosmos DB or Postgres for users.
