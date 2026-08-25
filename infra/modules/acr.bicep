// infra/modules/acr.bicep
param location string
param environmentName string

var acrName = replace('acr${environmentName}', '-', '')

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: { name: 'Standard' }
  properties: {
    adminUserEnabled: false  // credential-free by design, per Project 3's lesson
  }
}

output loginServer string = acr.properties.loginServer
output acrId string = acr.id
