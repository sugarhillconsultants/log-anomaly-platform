// infra/main.bicep
//
// Same overall pattern as Project 3 (Multi-Cloud MLOps Showcase), with
// one structural improvement learned from that project's debugging
// session: the useAcrImage circular-dependency toggle is included from
// the start here, not discovered after a failed first deployment.

targetScope = 'resourceGroup'

param environmentName string = 'log-anomaly'
param location string = resourceGroup().location
param useAcrImage bool = false

module logAnalytics 'modules/monitoring.bicep' = {
  name: 'monitoringDeployment'
  params: {
    location: location
    environmentName: environmentName
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acrDeployment'
  params: {
    location: location
    environmentName: environmentName
  }
}

module containerApp 'modules/container-app.bicep' = {
  name: 'containerAppDeployment'
  params: {
    location: location
    environmentName: environmentName
    acrLoginServer: acr.outputs.loginServer
    acrId: acr.outputs.acrId
    logAnalyticsWorkspaceId: logAnalytics.outputs.logAnalyticsWorkspaceId
    appInsightsConnectionString: logAnalytics.outputs.appInsightsConnectionString
    useAcrImage: useAcrImage
  }
}

output acrLoginServer string = acr.outputs.loginServer
output containerAppFqdn string = containerApp.outputs.fqdn
output containerAppName string = containerApp.outputs.containerAppName
// Needed by deploy/canary_rollback.py to query App Insights directly.
output logAnalyticsWorkspaceId string = logAnalytics.outputs.logAnalyticsWorkspaceId
