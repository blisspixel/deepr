// Deepr Azure Deployment - Security Hardened
// Deploy with: az deployment group create -g deepr-rg -f main.bicep

@description('Environment name')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'prod'

@description('Location for all resources')
param location string = resourceGroup().location

@description('OpenAI API Key')
@secure()
@minLength(1)
param openaiApiKey string

@description('Google API Key (optional)')
@secure()
param googleApiKey string = ''

@description('xAI API Key (optional)')
@secure()
param xaiApiKey string = ''

@description('Daily budget limit in USD')
@minValue(1)
@maxValue(10000)
param dailyBudget int = 50

@description('Monthly budget limit in USD')
@minValue(1)
@maxValue(100000)
param monthlyBudget int = 500

@description('Enable WAF on Application Gateway')
param enableWaf bool = true

@description('Allowed IP ranges for API access (CIDR notation)')
param allowedIpRanges array = []

var prefix = 'deepr-${environment}'
var uniqueSuffix = uniqueString(resourceGroup().id)

// Build IP security restrictions
var baseIpRestrictions = [
  {
    ipAddress: 'AzureCloud'
    action: 'Allow'
    tag: 'ServiceTag'
    priority: 100
    name: 'AllowAzureServices'
  }
]
var customIpRestrictions = [for (ip, i) in allowedIpRanges: {
  ipAddress: ip
  action: 'Allow'
  priority: 200 + i
  name: 'AllowedIP-${i}'
}]
var allIpRestrictions = concat(baseIpRestrictions, customIpRestrictions)

// ============================================================================
// Virtual Network with Subnets
// ============================================================================
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name: '${prefix}-vnet'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
    subnets: [
      {
        name: 'functions-subnet'
        properties: {
          addressPrefix: '10.0.1.0/24'
          delegations: [
            {
              name: 'functions-delegation'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
          serviceEndpoints: [
            { service: 'Microsoft.Storage' }
            { service: 'Microsoft.KeyVault' }
            { service: 'Microsoft.AzureCosmosDB' }
          ]
          networkSecurityGroup: {
            id: functionsNsg.id
          }
        }
      }
      {
        name: 'containers-subnet'
        properties: {
          addressPrefix: '10.0.2.0/24'
          serviceEndpoints: [
            { service: 'Microsoft.Storage' }
            { service: 'Microsoft.KeyVault' }
            { service: 'Microsoft.AzureCosmosDB' }
          ]
          networkSecurityGroup: {
            id: containersNsg.id
          }
        }
      }
      {
        name: 'private-endpoints-subnet'
        properties: {
          addressPrefix: '10.0.3.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'appgw-subnet'
        properties: {
          addressPrefix: '10.0.4.0/24'
        }
      }
    ]
  }
}

// ============================================================================
// Network Security Groups
// ============================================================================
resource functionsNsg 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: '${prefix}-functions-nsg'
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowHTTPS'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'AzureCloud'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource containersNsg 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: '${prefix}-containers-nsg'
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowHTTPSOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '443'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

// ============================================================================
// Key Vault with Private Endpoint
// ============================================================================
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${prefix}-kv-${uniqueSuffix}'
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      virtualNetworkRules: [
        {
          id: '${vnet.id}/subnets/functions-subnet'
        }
        {
          id: '${vnet.id}/subnets/containers-subnet'
        }
      ]
    }
  }
}

resource keyVaultPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${prefix}-kv-pe'
  location: location
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/private-endpoints-subnet'
    }
    privateLinkServiceConnections: [
      {
        name: 'keyVaultConnection'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource keyVaultPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
}

resource keyVaultPrivateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: keyVaultPrivateDnsZone
  name: '${prefix}-kv-dns-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource keyVaultPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  parent: keyVaultPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'config1'
        properties: {
          privateDnsZoneId: keyVaultPrivateDnsZone.id
        }
      }
    ]
  }
}

// Secrets
resource openaiSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'openai-api-key'
  properties: {
    value: openaiApiKey
    attributes: {
      enabled: true
    }
  }
}

resource googleSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(googleApiKey)) {
  parent: keyVault
  name: 'google-api-key'
  properties: {
    value: googleApiKey
    attributes: {
      enabled: true
    }
  }
}

resource xaiSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(xaiApiKey)) {
  parent: keyVault
  name: 'xai-api-key'
  properties: {
    value: xaiApiKey
    attributes: {
      enabled: true
    }
  }
}

// ============================================================================
// Storage Account with Private Endpoint and Encryption
// ============================================================================
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'deepr${uniqueSuffix}'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    allowSharedKeyAccess: false  // Require Azure AD auth
    encryption: {
      services: {
        blob: {
          enabled: true
          keyType: 'Account'
        }
        queue: {
          enabled: true
          keyType: 'Account'
        }
      }
      keySource: 'Microsoft.Storage'
    }
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      virtualNetworkRules: [
        {
          id: '${vnet.id}/subnets/functions-subnet'
        }
        {
          id: '${vnet.id}/subnets/containers-subnet'
        }
      ]
    }
  }
}

resource storagePrivateEndpointBlob 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${prefix}-storage-blob-pe'
  location: location
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/private-endpoints-subnet'
    }
    privateLinkServiceConnections: [
      {
        name: 'blobConnection'
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: ['blob']
        }
      }
    ]
  }
}

resource storagePrivateEndpointQueue 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${prefix}-storage-queue-pe'
  location: location
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/private-endpoints-subnet'
    }
    privateLinkServiceConnections: [
      {
        name: 'queueConnection'
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: ['queue']
        }
      }
    ]
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource jobQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-01-01' = {
  parent: queueService
  name: 'deepr-jobs'
}

resource dlqQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-01-01' = {
  parent: queueService
  name: 'deepr-jobs-dlq'
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 30
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 30
    }
  }
}

resource resultsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'results'
  properties: {
    publicAccess: 'None'
  }
}

// ============================================================================
// Cosmos DB for Job Metadata (replaces Storage Table for O(1) lookups)
// ============================================================================
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' = {
  name: '${prefix}-cosmos-${uniqueSuffix}'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    publicNetworkAccess: 'Disabled'
    isVirtualNetworkFilterEnabled: true
    virtualNetworkRules: [
      {
        id: '${vnet.id}/subnets/functions-subnet'
      }
      {
        id: '${vnet.id}/subnets/containers-subnet'
      }
    ]
    disableKeyBasedMetadataWriteAccess: true
  }
}

resource cosmosPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${prefix}-cosmos-pe'
  location: location
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/private-endpoints-subnet'
    }
    privateLinkServiceConnections: [
      {
        name: 'cosmosConnection'
        properties: {
          privateLinkServiceId: cosmosAccount.id
          groupIds: ['Sql']
        }
      }
    ]
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-04-15' = {
  parent: cosmosAccount
  name: 'deepr'
  properties: {
    resource: {
      id: 'deepr'
    }
  }
}

resource cosmosJobsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2023-04-15' = {
  parent: cosmosDatabase
  name: 'jobs'
  properties: {
    resource: {
      id: 'jobs'
      partitionKey: {
        paths: ['/job_id']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [
          {
            path: '/status/?'
          }
          {
            path: '/submitted_at/?'
          }
          {
            path: '/user_id/?'
          }
        ]
        excludedPaths: [
          {
            path: '/*'
          }
        ]
      }
      defaultTtl: 7776000  // 90 days in seconds
    }
    options: {
      autoscaleSettings: {
        maxThroughput: 4000
      }
    }
  }
}

// ============================================================================
// Log Analytics Workspace
// ============================================================================
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${prefix}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 90
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

// ============================================================================
// Application Insights
// ============================================================================
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ============================================================================
// Function App with VNet Integration
// ============================================================================
resource functionAppPlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: '${prefix}-plan'
  location: location
  sku: {
    name: 'EP1'  // Elastic Premium for VNet integration
    tier: 'ElasticPremium'
    capacity: 1
  }
  properties: {
    maximumElasticWorkerCount: 10
  }
}

resource functionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: '${prefix}-api'
  location: location
  kind: 'functionapp'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: functionAppPlan.id
    httpsOnly: true
    virtualNetworkSubnetId: '${vnet.id}/subnets/functions-subnet'
    siteConfig: {
      pythonVersion: '3.11'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      http20Enabled: true
      vnetRouteAllEnabled: true
      ipSecurityRestrictions: allIpRestrictions
      appSettings: [
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storageAccount.name
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'STORAGE_ACCOUNT_NAME'
          value: storageAccount.name
        }
        {
          name: 'QUEUE_NAME'
          value: jobQueue.name
        }
        {
          name: 'RESULTS_CONTAINER'
          value: resultsContainer.name
        }
        {
          name: 'KEY_VAULT_URI'
          value: keyVault.properties.vaultUri
        }
        {
          name: 'COSMOS_ENDPOINT'
          value: cosmosAccount.properties.documentEndpoint
        }
        {
          name: 'COSMOS_DATABASE'
          value: cosmosDatabase.name
        }
        {
          name: 'DEEPR_BUDGET_DAILY'
          value: string(dailyBudget)
        }
        {
          name: 'DEEPR_BUDGET_MONTHLY'
          value: string(monthlyBudget)
        }
        {
          name: 'LOG_LEVEL'
          value: 'INFO'
        }
      ]
    }
  }
}

// Diagnostic settings for Function App
resource functionAppDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'functionAppDiagnostics'
  scope: functionApp
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      {
        category: 'FunctionAppLogs'
        enabled: true
        retentionPolicy: {
          days: 30
          enabled: true
        }
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          days: 30
          enabled: true
        }
      }
    ]
  }
}

// RBAC assignments for Function App
resource functionKeyVaultAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, functionApp.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionStorageBlobAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionStorageQueueAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, 'Storage Queue Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '974c5e8b-45b9-4653-ba55-5f855dd0fb88')
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cosmos DB SQL Role Assignment for Function App (data plane access)
resource functionCosmosRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2023-04-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, functionApp.id, 'Cosmos DB Data Contributor')
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'  // Built-in Data Contributor
    principalId: functionApp.identity.principalId
    scope: cosmosAccount.id
  }
}

// ============================================================================
// Container App Environment with VNet Integration
// ============================================================================
resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${prefix}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: '${vnet.id}/subnets/containers-subnet'
      internal: true
    }
    zoneRedundant: false
  }
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${prefix}-worker'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: []
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: 'mcr.microsoft.com/azure-functions/python:4-python3.11'
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            {
              name: 'STORAGE_ACCOUNT_NAME'
              value: storageAccount.name
            }
            {
              name: 'QUEUE_NAME'
              value: jobQueue.name
            }
            {
              name: 'RESULTS_CONTAINER'
              value: resultsContainer.name
            }
            {
              name: 'KEY_VAULT_URI'
              value: keyVault.properties.vaultUri
            }
            {
              name: 'COSMOS_ENDPOINT'
              value: cosmosAccount.properties.documentEndpoint
            }
            {
              name: 'COSMOS_DATABASE'
              value: cosmosDatabase.name
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8080
              }
              initialDelaySeconds: 30
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 10
        rules: [
          {
            name: 'cpu-scaling'
            custom: {
              type: 'cpu'
              metadata: {
                type: 'Utilization'
                value: '70'
              }
            }
          }
        ]
      }
    }
  }
}

// RBAC for Container App
resource containerKeyVaultAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, containerApp.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource containerStorageBlobAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, containerApp.id, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource containerStorageQueueAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, containerApp.id, 'Storage Queue Data Message Processor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8a0f0c08-91a1-4084-bc3d-661d67233fed')
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cosmos DB SQL Role Assignment for Container App (data plane access)
resource containerCosmosRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2023-04-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, containerApp.id, 'Cosmos DB Data Contributor')
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'  // Built-in Data Contributor
    principalId: containerApp.identity.principalId
    scope: cosmosAccount.id
  }
}

// ============================================================================
// Application Gateway with WAF
// ============================================================================
resource publicIp 'Microsoft.Network/publicIPAddresses@2023-05-01' = {
  name: '${prefix}-appgw-pip'
  location: location
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: '${prefix}-api-${uniqueSuffix}'
    }
  }
}

resource wafPolicy 'Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies@2023-05-01' = if (enableWaf) {
  name: '${prefix}-waf-policy'
  location: location
  properties: {
    policySettings: {
      requestBodyCheck: true
      maxRequestBodySizeInKb: 128
      fileUploadLimitInMb: 100
      state: 'Enabled'
      mode: 'Prevention'
    }
    managedRules: {
      managedRuleSets: [
        {
          ruleSetType: 'OWASP'
          ruleSetVersion: '3.2'
        }
        {
          ruleSetType: 'Microsoft_BotManagerRuleSet'
          ruleSetVersion: '1.0'
        }
      ]
    }
    customRules: [
      {
        name: 'RateLimitRule'
        priority: 1
        ruleType: 'RateLimitRule'
        rateLimitDuration: 'OneMin'
        rateLimitThreshold: 100
        matchConditions: [
          {
            matchVariables: [
              {
                variableName: 'RemoteAddr'
              }
            ]
            operator: 'IPMatch'
            negationConditon: true
            matchValues: ['0.0.0.0/0']
          }
        ]
        action: 'Block'
      }
    ]
  }
}

resource appGateway 'Microsoft.Network/applicationGateways@2023-05-01' = {
  name: '${prefix}-appgw'
  location: location
  properties: {
    sku: {
      name: enableWaf ? 'WAF_v2' : 'Standard_v2'
      tier: enableWaf ? 'WAF_v2' : 'Standard_v2'
      capacity: 2
    }
    firewallPolicy: enableWaf ? { id: wafPolicy.id } : null
    gatewayIPConfigurations: [
      {
        name: 'appGatewayIpConfig'
        properties: {
          subnet: {
            id: '${vnet.id}/subnets/appgw-subnet'
          }
        }
      }
    ]
    frontendIPConfigurations: [
      {
        name: 'appGwPublicFrontendIp'
        properties: {
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
    frontendPorts: [
      {
        name: 'port_443'
        properties: {
          port: 443
        }
      }
    ]
    backendAddressPools: [
      {
        name: 'functionBackendPool'
        properties: {
          backendAddresses: [
            {
              fqdn: functionApp.properties.defaultHostName
            }
          ]
        }
      }
    ]
    backendHttpSettingsCollection: [
      {
        name: 'functionHttpSettings'
        properties: {
          port: 443
          protocol: 'Https'
          cookieBasedAffinity: 'Disabled'
          pickHostNameFromBackendAddress: true
          requestTimeout: 300
        }
      }
    ]
    httpListeners: [
      {
        name: 'httpsListener'
        properties: {
          frontendIPConfiguration: {
            id: resourceId('Microsoft.Network/applicationGateways/frontendIPConfigurations', '${prefix}-appgw', 'appGwPublicFrontendIp')
          }
          frontendPort: {
            id: resourceId('Microsoft.Network/applicationGateways/frontendPorts', '${prefix}-appgw', 'port_443')
          }
          protocol: 'Https'
          sslCertificate: null  // Add SSL certificate in production
        }
      }
    ]
    requestRoutingRules: [
      {
        name: 'routeToFunction'
        properties: {
          priority: 100
          ruleType: 'Basic'
          httpListener: {
            id: resourceId('Microsoft.Network/applicationGateways/httpListeners', '${prefix}-appgw', 'httpsListener')
          }
          backendAddressPool: {
            id: resourceId('Microsoft.Network/applicationGateways/backendAddressPools', '${prefix}-appgw', 'functionBackendPool')
          }
          backendHttpSettings: {
            id: resourceId('Microsoft.Network/applicationGateways/backendHttpSettingsCollection', '${prefix}-appgw', 'functionHttpSettings')
          }
        }
      }
    ]
  }
}

// Diagnostic settings for App Gateway
resource appGatewayDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'appGatewayDiagnostics'
  scope: appGateway
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      {
        category: 'ApplicationGatewayAccessLog'
        enabled: true
      }
      {
        category: 'ApplicationGatewayPerformanceLog'
        enabled: true
      }
      {
        category: 'ApplicationGatewayFirewallLog'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// ============================================================================
// Security Alerts
// ============================================================================
resource highErrorRateAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${prefix}-high-error-rate'
  location: 'global'
  properties: {
    description: 'High error rate detected in API'
    severity: 2
    enabled: true
    scopes: [functionApp.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'Http5xxErrors'
          metricName: 'Http5xx'
          operator: 'GreaterThan'
          threshold: 10
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
  }
}

// ============================================================================
// Outputs
// ============================================================================
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output appGatewayUrl string = 'https://${publicIp.properties.dnsSettings.fqdn}'
output keyVaultName string = keyVault.name
output storageAccountName string = storageAccount.name
output cosmosAccountName string = cosmosAccount.name
output containerAppName string = containerApp.name
output vnetId string = vnet.id
