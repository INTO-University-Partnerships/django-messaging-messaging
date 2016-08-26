'use strict';

var app = angular.module('notificationsApp.controllers', []);

app.controller('listNotificationsCtrl', [
    '$scope', '$timeout', '$window', 'genericSrv', 'messageSrv', 'CONFIG',
    function ($scope, $timeout, $window, genericSrv, messageSrv, config) {
        $scope.perPage = 6;
        $scope.notifications = null;
        $scope.total = 0;
        $scope.currentPage = 0;
        $scope.timeoutPromise = null;
        $scope.messages = messageSrv.collect();
        $scope.showMessageItemIds = config.showMessageItemIds;
        $scope.firstTime = true;

        $scope.getPageOfNotifications = function () {
            var url = Urls['messaging_api:get_notifications']() +
                '?page=' + $scope.currentPage +
                '&per_page=' + $scope.perPage;
            $timeout.cancel($scope.timeoutPromise);
            genericSrv.genericGet(url).
                then(function (data) {
                    $scope.notifications = data.notifications;
                    $scope.total = data.total;
                    if ($scope.firstTime && $scope.total === 0) {
                        $scope.firstTime = false;
                        $scope.messages.info = config.trans.no_notifications;
                    }
                }, function (error) {
                    $scope.notifications = null;
                    $scope.total = 0;
                    $scope.messages.danger = error.errorMessage;
                }).
                finally(function () {
                    $scope.timeoutPromise = $timeout(function () {
                        $scope.getPageOfNotifications($scope.currentPage);
                    }, 10000);
                });
        };

        $scope.clickNotification = function (notification) {
            var url = Urls['messaging_api:mark_notification_read']() + '?miid=' + notification.id;
            genericSrv.genericGet(url).
                then(function () {
                    $window.location.href = notification.url;
                }, function (error) {
                    $scope.messages.danger = error.errorMessage;
                });
        };

        $scope.openModal = function ($event, uid, miid) {
            $event.stopPropagation();
            $timeout.cancel($scope.timeoutPromise);
            $scope.miid = miid;
            jQuery('#' + uid).modal({});
        };

        $scope.cancelDeleteNotification = function (uid) {
            var elem = jQuery('#' + uid);
            elem.off('hidden.bs.modal');
            elem.on('hidden.bs.modal', function () {
                $scope.getPageOfNotifications($scope.currentPage);
            });
            elem.modal('hide');
        };

        $scope.deleteNotification = function (uid) {
            var url,
                elem = jQuery('#' + uid);
            elem.off('hidden.bs.modal');
            elem.on('hidden.bs.modal', function () {
                var miid = $scope.miid;
                $scope.miid = null;
                if (!miid) {
                    return;
                }
                url = Urls['messaging_api:delete_message_item']() + '?miid=' + miid;
                genericSrv.genericGet(url).
                    then(function (data) {
                        $scope.messages.success = data.successMessage;
                        $scope.currentPage = 0;
                    }, function (error) {
                        $scope.messages[error.type] = error.errorMessage;
                    }).
                    finally(function () {
                        $scope.getPageOfNotifications($scope.currentPage);
                    });
            });
            elem.modal('hide');
        };

        $scope.$watch('currentPage', function (newValue) {
            $scope.getPageOfNotifications(newValue);
        });

        $scope.$on('$destroy', function () {
            $timeout.cancel($scope.timeoutPromise);
        });
    }
]);
