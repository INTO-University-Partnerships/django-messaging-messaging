'use strict';

var app = angular.module('messagingApp', [
    'messagingApp.controllers',
    'messagingApp.services',
    'general.directives',
    'general.filters',
    'general.services',
    'ngRoute',
    'ngSanitize'
]);

app.constant('CONFIG', window.CONFIG);
delete window.CONFIG;

app.config([
    '$routeProvider', '$httpProvider',
    function ($routeProvider, $httpProvider) {
        $httpProvider.defaults.xsrfCookieName = 'csrftoken';
        $httpProvider.defaults.xsrfHeaderName = 'X-CSRFToken';
        $httpProvider.defaults.headers.common['X-Requested-With'] = 'XMLHttpRequest';
        $routeProvider.
            when('/', {
                templateUrl: Urls['messaging_api:partial_base']() + 'route/listMessages',
                controller: 'listMessagesCtrl'
            }).
            when('/compose', {
                templateUrl: Urls['messaging_api:partial_base']() + 'route/composeMessage',
                controller: 'composeMessageCtrl'
            }).
            when('/reply/:id', {
                templateUrl: Urls['messaging_api:partial_base']() + 'route/composeMessage',
                controller: 'composeMessageCtrl'
            }).
            when('/read/:id', {
                templateUrl: Urls['messaging_api:partial_base']() + 'route/readThread',
                controller: 'readThreadCtrl'
            }).
            otherwise({
                redirectTo: '/'
            });
    }
]);
