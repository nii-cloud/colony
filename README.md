Welcome to Colony project.


# Introduction

Colony is a project which federate cloud services. The fisrt target is the federation of object services,
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
* Swift Continer's ACL and Metadata(including publicicate HTML)  support
* Swift Object's metadata support
* Pluggable feature - Sysadmin can disable OpenStack compute service features to allow users only to use object services
* multi account(tenant) support - User can access an account(tenant) which is not belonged to your account
* Multibyte support - User can use multibyte characters for containers/objects
* supports to upload files more than 5G support.


## Colony-Keystone

based on Keystone with some modifications to provide the federation of object services.

* In addition to %{tenant_id}, %{tenant_name} can be used for endpointTemplates
* provides auth_token_for_colony.py middleware for swift
* Can be authenticated with Shibbleth 
* Provides a swift filter to proxy for keystone auth

## Colony-Dispatcher

Colony-Dispatcher is a proxy for swift proxy that support following features

* Relay requests to multiple object services (and merge response for clients)
* Relay requests to a specific object service indicated by URI
* LoadBalance - determine the nearest Swift proxy server to relay requests
* User can use x-copy-from/to feature between different Swift services. 


## Colony-Utilities

Tools to make admin task easier to provide the federation of object services

* swift-ring-sync
