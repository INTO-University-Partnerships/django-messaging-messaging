'use strict';

var app = angular.module('general.directives', []);

app.directive('alerts', [
    function () {
        return {
            restrict: 'E',
            scope: {
                messages: '='
            },
            templateUrl: Urls['messaging_api:partial_base']() + 'directive/alerts',
            link: function (scope, element) {
                element.find('button').bind('click', function () {
                    scope.$apply(function () {
                        scope.class = '';
                        scope.msg = '';
                    });
                });
            },
            controller: ['$scope', function ($scope) {
                $scope.class = '';

                $scope.setMessage = function (status) {
                    if ($scope.messages[status]) {
                        $scope.msg = $scope.messages[status];
                        $scope.class = 'alert-' + status;
                        $scope.messages = {};
                    }
                };

                angular.forEach(['success', 'danger', 'warning', 'info'], function (status) {
                    $scope.$watch('messages.' + status, function () {
                        $scope.setMessage(status);
                    }, true);
                });
            }]
        };
    }
]);

app.directive('modalConfirm', [
    function () {
        return {
            restrict: 'E',
            scope: {
                uid: '@',
                title: '@',
                body: '@',
                cancel: '&',
                confirm: '&'
            },
            templateUrl: Urls['messaging_api:partial_base']() + 'directive/modalConfirm'
        };
    }
]);

app.directive('pagination', [
    function () {
        return {
            restrict: 'E',
            scope: {
                perPage: '@',
                currentPage: '=',
                total: '=',
                fetchPage: '&'
            },
            templateUrl: Urls['messaging_api:partial_base']() + 'directive/pagination',
            controller: ['$scope', function ($scope) {
                $scope.currentPage = 0;
                $scope.pageCount = 0;
                $scope.pages = [];

                $scope.calculatePageCount = function () {
                    if ($scope.total === 0) {
                        $scope.pageCount = 1;
                    } else {
                        $scope.pageCount = Math.ceil($scope.total / $scope.perPage);
                    }
                };

                $scope.calculatePages = function () {
                    var from, to, i;
                    from = 1;
                    to = $scope.pageCount;
                    $scope.pages = [];
                    for (i = from; i <= to; ++i) {
                        $scope.pages.push(i);
                    }
                };

                $scope.$watch('currentPage', function () {
                    $scope.calculatePages();
                });

                $scope.$watch('total', function () {
                    $scope.calculatePageCount();
                    $scope.calculatePages();
                });

                $scope.prevPage = function () {
                    if ($scope.currentPage > 0) {
                        --$scope.currentPage;
                    }
                };

                $scope.prevPageDisabled = function () {
                    var disabled = $scope.currentPage === 0 ? 'disabled' : '';
                    return disabled;
                };

                $scope.nextPage = function () {
                    if ($scope.currentPage < $scope.pageCount - 1) {
                        $scope.currentPage++;
                    }
                };

                $scope.nextPageDisabled = function () {
                    var disabled = $scope.currentPage === $scope.pageCount - 1 ? 'disabled' : '';
                    return disabled;
                };

                $scope.pageDisabled = function (n) {
                    var disabled = $scope.currentPage === n;
                    return disabled;
                };

                $scope.gotoPage = function (n) {
                    $scope.currentPage = n;
                };
            }]
        };
    }
]);
