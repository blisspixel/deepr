// Hosted Deepr MCP HTTP endpoint on Azure Container Apps.
// This template does not create provider API secrets. Add provider keys only
// when a scoped key mode and budget intentionally allow paid research tools.

@description('Environment name used in resource names.')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string = 'prod'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Container image built from deploy/mcp-http/Dockerfile.')
param containerImage string

@description('Expose Container Apps ingress publicly. Keep false until DNS, TLS, scoped keys, and IP restrictions are ready.')
param externalIngress bool = false

@description('Optional CIDR allowlist for public ingress. Leave empty for private ingress or provider-managed access controls.')
param allowedIpRanges array = []

@description('Optional first-boot shared token. Scoped keys remain the production path because they carry mode, budget, rate limit, and audit metadata.')
@secure()
param initialSharedAuthToken string = ''

@description('Optional container registry server, for example ghcr.io or myregistry.azurecr.io.')
param registryServer string = ''

@description('Optional container registry username.')
param registryUsername string = ''

@description('Optional container registry password.')
@secure()
param registryPassword string = ''

@description('Container CPU cores.')
@allowed([
  '0.5'
  '1.0'
  '2.0'
])
param cpu string = '1.0'

@description('Container memory.')
@allowed([
  '1Gi'
  '2Gi'
  '4Gi'
])
param memory string = '2Gi'

@description('Minimum replicas. Use 0 for lower idle cost or 1 to avoid cold starts.')
@minValue(0)
@maxValue(10)
param minReplicas int = 0

@description('Maximum replicas.')
@minValue(1)
@maxValue(20)
param maxReplicas int = 3

@description('Maximum simultaneous HTTP POST requests per Deepr MCP container before returning 429. Also used by the Container Apps HTTP scale rule.')
@minValue(1)
@maxValue(1000)
param maxConcurrentRequests int = 32

@description('Azure Files quota for Deepr data, keys, reports, and audit logs.')
@minValue(1)
@maxValue(1024)
param fileShareQuotaGiB int = 32

var prefix = 'deepr-mcp-${environment}'
var uniqueSuffix = uniqueString(resourceGroup().id, environment)
var storageAccountName = toLower('dpmcp${uniqueSuffix}')
var fileShareName = 'deepr-data'
var hasBootstrapToken = !empty(initialSharedAuthToken)
var hasRegistryCredentials = !empty(registryServer) && !empty(registryUsername) && !empty(registryPassword)
var authSecrets = hasBootstrapToken ? [
  {
    name: 'mcp-auth-token'
    value: initialSharedAuthToken
  }
] : []
var registrySecrets = hasRegistryCredentials ? [
  {
    name: 'registry-password'
    value: registryPassword
  }
] : []
var authEnv = hasBootstrapToken ? [
  {
    name: 'DEEPR_MCP_AUTH_TOKEN'
    secretRef: 'mcp-auth-token'
  }
] : []

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs-${uniqueSuffix}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    supportsHttpsTrafficOnly: true
    encryption: {
      services: {
        file: {
          enabled: true
          keyType: 'Account'
        }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource dataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: fileShareName
  properties: {
    enabledProtocols: 'SMB'
    shareQuota: fileShareQuotaGiB
  }
}

resource containerEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-env-${uniqueSuffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerEnvironment
  name: 'deepr-data'
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: dataShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource mcpContainerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-http-${uniqueSuffix}'
  location: location
  properties: {
    managedEnvironmentId: containerEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: concat(authSecrets, registrySecrets)
      registries: hasRegistryCredentials ? [
        {
          server: registryServer
          username: registryUsername
          passwordSecretRef: 'registry-password'
        }
      ] : []
      ingress: {
        external: externalIngress
        targetPort: 8765
        transport: 'auto'
        allowInsecure: false
        ipSecurityRestrictions: [for (range, i) in allowedIpRanges: {
          name: 'allowed-${i}'
          action: 'Allow'
          ipAddressRange: range
          description: 'Allowed remote MCP caller CIDR'
        }]
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
    }
    template: {
      containers: [
        {
          name: 'deepr-mcp-http'
          image: containerImage
          command: [
            'deepr'
          ]
          args: [
            'mcp'
            'serve'
            '--http'
            '--host'
            '0.0.0.0'
            '--port'
            '8765'
            '--path'
            '/mcp'
            '--keys-path'
            '/data/security/mcp_keys.json'
          ]
          env: concat([
            {
              name: 'DEEPR_DATA_DIR'
              value: '/data'
            }
            {
              name: 'DEEPR_REPORTS_PATH'
              value: '/data/reports'
            }
            {
              name: 'DEEPR_MCP_KEYS_PATH'
              value: '/data/security/mcp_keys.json'
            }
            {
              name: 'DEEPR_MCP_HTTP_MAX_CONCURRENCY'
              value: string(maxConcurrentRequests)
            }
            {
              name: 'DEEPR_COST_TRACKING_STRICT'
              value: '1'
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
          ], authEnv)
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          volumeMounts: [
            {
              volumeName: 'deepr-data'
              mountPath: '/data'
            }
          ]
          probes: [
            {
              type: 'Readiness'
              httpGet: {
                path: '/mcp/health'
                port: 8765
              }
              initialDelaySeconds: 10
              periodSeconds: 15
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/mcp/health'
                port: 8765
              }
              initialDelaySeconds: 30
              periodSeconds: 30
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'deepr-data'
          storageType: 'AzureFile'
          storageName: environmentStorage.name
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: string(maxConcurrentRequests)
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppName string = mcpContainerApp.name
output managedEnvironmentName string = containerEnvironment.name
output storageAccountName string = storageAccount.name
output fileShareName string = dataShare.name
output mcpEndpoint string = 'https://${mcpContainerApp.properties.configuration.ingress.fqdn}/mcp'
