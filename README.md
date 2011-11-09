Welcome to Colony project.


# Introduction

Colony is a project which federatea cloud services. The fisrt target is the federation of object services,
like swift.

# Features

Colony consists of 4 components to provide the federation of object services

* Horizon
* Keystone
* Dispatcher
* Utilities

## Colony-Horizon

based on Openstack Dashboard with some extra features

* multi region support - User can choose which object service is used to store/retrieve objects among regions
* Swift ACL and Metadata support
* Pluggable feature - Sysadmin can disable OpenStack compute service features to allow users only to use object services

## Colony-Keystone

based on Keystone with some modifications to provide the federation of object services.

* In addition to %{tenant_id}, %{tenant_name} can be used for endpointTemplates


## Colony-Dispatcher

## Colony-Utilities
