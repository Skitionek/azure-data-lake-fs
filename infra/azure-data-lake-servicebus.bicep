targetScope = 'resourceGroup'

@description('Location for resources.')
param location string = resourceGroup().location

@description('Unique prefix for resource names.')
@minLength(3)
@maxLength(11)
param namePrefix string

@description('Service Bus queue name used for change events.')
param queueName string = 'adlfs-events'

@description('Optional tags to apply to all resources.')
param tags object = {}

var storageAccountName = toLower('${namePrefix}adls')
var serviceBusNamespaceName = toLower('${namePrefix}sb')
var systemTopicName = '${namePrefix}-stg-events'
var eventSubscriptionName = 'storage-to-servicebus'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    isHnsEnabled: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
  }
}

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: serviceBusNamespaceName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
}

resource serviceBusQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: queueName
  properties: {
    requiresDuplicateDetection: false
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 10
    lockDuration: 'PT1M'
  }
}

resource systemTopic 'Microsoft.EventGrid/systemTopics@2023-12-15-preview' = {
  name: systemTopicName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    source: storageAccount.id
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

resource eventSubscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2023-12-15-preview' = {
  parent: systemTopic
  name: eventSubscriptionName
  properties: {
    destination: {
      endpointType: 'ServiceBusQueue'
      properties: {
        resourceId: serviceBusQueue.id
      }
    }
    filter: {
      includedEventTypes: [
        'Microsoft.Storage.BlobCreated'
        'Microsoft.Storage.BlobDeleted'
      ]
      enableAdvancedFilteringOnArrays: true
    }
    retryPolicy: {
      maxDeliveryAttempts: 5
      eventTimeToLiveInMinutes: 1440
    }
  }
}

output storageAccountId string = storageAccount.id
output dataLakeFileSystemEndpoint string = storageAccount.properties.primaryEndpoints.dfs
output serviceBusNamespaceId string = serviceBusNamespace.id
output serviceBusQueueId string = serviceBusQueue.id
