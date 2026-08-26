// infra/modules/container-app.bicep
//
// Includes, from the start, the two fixes Project 3 only discovered
// after a failed first deployment: a useAcrImage toggle to break the
// managed-identity/AcrPull circular dependency, and a readiness probe
// that's conditional on which image is actually running (the public
// placeholder used for the first deploy doesn't listen on port 7860,
// so probing it unconditionally would strand the app at 0 replicas).

param location string
param environmentName string
param acrLoginServer string
param acrId string
param logAnalyticsWorkspaceId string
param appInsightsConnectionString string
param initialImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param useAcrImage bool = false

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: last(split(logAnalyticsWorkspaceId, '/'))
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${environmentName}'
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

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${environmentName}'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      // Required for deploy/canary_rollback.py to work at all: in the
      // default 'Single' mode, any newly deployed revision is
      // automatically promoted to 100% traffic immediately, making a
      // genuine canary split architecturally impossible. 'Multiple'
      // mode allows two revisions to coexist with independently
      // controlled traffic weights.
      activeRevisionsMode: 'Multiple'
      ingress: {
        external: true
        targetPort: 7860
        traffic: [ { latestRevision: true, weight: 100 } ]
      }
      registries: useAcrImage ? [
        { server: acrLoginServer, identity: 'system' }
      ] : []
    }
    template: {
      containers: [
        {
          name: 'log-anomaly-platform'
          image: useAcrImage ? '${acrLoginServer}/log-anomaly-platform:latest' : initialImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
          ]
          probes: useAcrImage ? [
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 7860 }
              initialDelaySeconds: 10
              periodSeconds: 5
            }
          ] : []
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }  // minReplicas:1, not 0 — avoids
                                                   // the cold-start 504s hit in Project 3
    }
  }
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrId, containerApp.id, 'AcrPull')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppName string = containerApp.name
