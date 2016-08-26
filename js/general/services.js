'use strict';

var app = angular.module('general.services', []);

app.service('genericSrv', [
    '$http', '$q',
    function ($http, $q) {
        this.genericGet = function (url) {
            return this._genericVerb('get', url, {});
        };

        this.genericPost = function (url, data) {
            return this._genericVerb('post', url, data);
        };

        this._genericVerb = function (verb, url, data) {
            var deferred = $q.defer();
            $http[verb](url, data).
                success(function (d) {
                    deferred.resolve(d);
                }).
                error(function (d) {
                    deferred.reject(d);
                });
            return deferred.promise;
        };
    }
]);

app.service('messageSrv', function () {
    this.messages = {};
    this.collect = function () {
        var retval = {};
        angular.copy(this.messages, retval);
        this.messages = {};
        return retval;
    };
});
