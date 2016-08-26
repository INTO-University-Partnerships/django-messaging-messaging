'use strict';

var app = angular.module('general.filters', []);

app.filter('raw', [
    '$sce',
    function ($sce) {
        return function (untrusted) {
            return $sce.trustAsHtml(untrusted);
        };
    }
]);
