'use strict';

var app = angular.module('notificationsApp', [
    'notificationsApp.controllers',
    'notificationsApp.services',
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
                templateUrl: Urls['messaging_api:partial_base']() + 'route/listNotifications',
                controller: 'listNotificationsCtrl'
            }).
            otherwise({
                redirectTo: '/'
            });
    }
]);
