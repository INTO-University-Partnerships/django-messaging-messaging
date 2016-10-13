'use strict';

var app = angular.module('messagingApp.controllers', []);

app.controller('listMessagesCtrl', [
    '$scope', '$timeout', 'genericSrv', 'messageSrv', 'inboxSortSrv', 'CONFIG',
    function ($scope, $timeout, genericSrv, messageSrv, inboxSortSrv, config) {
        $scope.perPage = 10;
        $scope.inbox = null;
        $scope.total = 0;
        $scope.currentPage = 0;
        $scope.timeoutPromise = null;
        $scope.messages = messageSrv.collect();
        $scope.sort = inboxSortSrv.toFlags();
        $scope.showMessageItemIds = config.showMessageItemIds;
        $scope.firstTime = true;

        $scope.getPageOfInbox = function () {
            var url = Urls['messaging_api:get_inbox']() +
                '?page=' + $scope.currentPage +
                '&per_page=' + $scope.perPage +
                '&sort_field=' + inboxSortSrv.sortField +
                '&sort_dir=' + inboxSortSrv.sortDirection;
            $timeout.cancel($scope.timeoutPromise);
            genericSrv.genericGet(url).
                then(function (data) {
                    $scope.inbox = data.messages;
                    $scope.total = data.total;
                    if ($scope.firstTime && $scope.total === 0) {
                        $scope.firstTime = false;
                        $scope.messages.info = config.trans.empty_inbox;
                    }
                }, function (error) {
                    $scope.inbox = null;
                    $scope.total = 0;
                    $scope.messages.danger = error.errorMessage;
                }).
                finally(function () {
                    $scope.timeoutPromise = $timeout(function () {
                        $scope.getPageOfInbox($scope.currentPage);
                    }, 10000);
                });
        };

        $scope.setSort = function (field) {
            if (field === inboxSortSrv.sortField) {
                inboxSortSrv.toggleSortDirection();
            } else {
                inboxSortSrv.sortField = field;
            }
            $scope.sort = inboxSortSrv.toFlags();
            $scope.getPageOfInbox($scope.currentPage);
        };

        $scope.$watch('currentPage', function (newValue) {
            $scope.getPageOfInbox(newValue);
        });

        $scope.$on('$destroy', function () {
            $timeout.cancel($scope.timeoutPromise);
        });
    }
]);

app.controller('composeMessageCtrl', [
    '$scope', '$timeout', '$location', '$routeParams', 'genericSrv', 'messageSrv', 'CONFIG',
    function ($scope, $timeout, $location, $routeParams, genericSrv, messageSrv, config) {
        $scope.timeoutPromise = $scope.sendTo = $scope.sendToChoices = null;
        $scope.currentPage = $scope.pageCount = $scope.sendToChoicesCount = 0;
        $scope.pages = [];
        $scope.messages = messageSrv.collect();
        $scope.searching = false;
        $scope.minSearchChars = config.minSearchChars;
        $scope.isSuperUser = config.isSuperUser;
        $scope.replySender = null;
        $scope.replyTo = $scope.replyBody = '';
        $scope.newMessage = false;
        $scope.msg = {
            recipients: [],
            targetAll: false,
            subject: '',
            body: '',
            miid: $routeParams.id ? $routeParams.id : 0
        };

        if ($scope.msg.miid) {
            var url = Urls['messaging_api:get_reply_info']() + '?miid=' + $scope.msg.miid;
            genericSrv.genericGet(url).
                then(function (data) {
                    $scope.msg.recipients = data.recipients;
                    $scope.msg.subject = data.subject;
                    $scope.replySender = data.recipients[0];
                    $scope.replyTo = data.sender;
                    $scope.replyBody = data.body;
                }, function (error) {
                    messageSrv.messages[error.type] = error.errorMessage;
                    $location.path('/read/' + $scope.msg.miid);
                });
        } else {
            $scope.newMessage = true;
        }

        $scope.sendToKeyUp = function () {
            $timeout.cancel($scope.timeoutPromise);
            $scope.timeoutPromise = $timeout(function () {
                $scope.searchRecipient();
            }, 500);
        };

        $scope.searchRecipient = function () {
            var d;
            if (!$scope.sendTo) {
                return;
            }
            if ($scope.sendTo.length >= $scope.minSearchChars) {
                $scope.searching = true;
                d = {
                    q: $scope.sendTo,
                    recipients: $scope.msg.recipients,
                    page: $scope.currentPage
                };
                genericSrv.genericPost(Urls['messaging_api:search_recipient'](), d).
                    then(function (data) {
                        $scope.addChoices(data);
                    }, function (error) {
                        $scope.messages.danger = error.errorMessage;
                        $scope.sendToChoices = null;
                    }).
                    finally(function () {
                        $scope.searching = false;
                    });
            } else if ($scope.sendTo.length < $scope.minSearchChars) {
                $scope.sendToChoices = null;
            }
        };

        $scope.addRecipient = function (choice) {
            $scope.msg.recipients.push(choice);
            $scope.removeChoice(choice);
            $scope.searchRecipient();
        };

        $scope.removeRecipient = function (recipient) {
            $scope.msg.recipients = $scope.msg.recipients.filter(function (value) {
                return value.id !== recipient.id;
            });
            $scope.searchRecipient();
        };

        $scope.addChoices = function (data) {
            var j;
            $scope.sendToChoices = data.searchResults.filter(function (value) {
                var i, count;
                for (i = 0, count = $scope.msg.recipients.length; i < count; ++i) {
                    if ($scope.msg.recipients[i].id === value.id) {
                        return false;
                    }
                }
                return true;
            });
            $scope.sendToChoicesCount = data.count;
            $scope.pageCount = Math.ceil(data.count / data.perPage);
            $scope.pages = [];
            for (j = 1; j <= $scope.pageCount; ++j) {
                $scope.pages.push(j);
            }
        };

        $scope.removeChoice = function (choice) {
            $scope.sendToChoices = $scope.sendToChoices.filter(function (value) {
                return value.id !== choice.id;
            });
        };

        $scope.targetAllChanged = function () {
            if ($scope.msg && $scope.msg.targetAll) {
                $scope.sendTo = '';
                $scope.sendToChoices = [];
                $scope.msg.recipients = [];
            }
        };

        $scope.sendMessage = function () {
            genericSrv.genericPost(Urls['messaging_api:send_message'](), $scope.msg).
                then(function (data) {
                    messageSrv.messages.success = data.successMessage;
                    if ($scope.msg.miid) {
                        $location.path('/read/' + $scope.msg.miid);
                    } else {
                        $location.path('/');
                    }
                }, function (error) {
                    messageSrv.messages[error.type] = error.errorMessage;
                    $location.path('/');
                });
        };

        $scope.isSender = function (recipient) {
            if (!$scope.msg.miid || !$scope.replySender) {
                return false;
            }
            return recipient.id === $scope.replySender.id;
        };

        $scope.$on('$destroy', function () {
            $timeout.cancel($scope.timeoutPromise);
        });

        $scope.prevPage = function () {
            if ($scope.currentPage > 0) {
                --$scope.currentPage;
                $scope.searchRecipient();
            }
        };

        $scope.prevPageDisabled = function () {
            var disabled = $scope.currentPage === 0 ? 'disabled' : '';
            return disabled;
        };

        $scope.nextPage = function () {
            if ($scope.currentPage < $scope.pageCount - 1) {
                $scope.currentPage++;
                $scope.searchRecipient();
            }
        };

        $scope.nextPageDisabled = function () {
            var disabled = $scope.currentPage === $scope.pageCount - 1 ? 'disabled' : '';
            return disabled;
        };

        $scope.pageDisabled = function (n) {
            return $scope.currentPage === n;
        };

        $scope.gotoPage = function (n) {
            $scope.currentPage = n;
            $scope.searchRecipient();
        };
    }
]);

app.controller('readThreadCtrl', [
    '$scope', '$timeout', '$location', '$routeParams', 'genericSrv', 'messageSrv', 'CONFIG',
    function ($scope, $timeout, $location, $routeParams, genericSrv, messageSrv, config) {
        $scope.messageItemId = $routeParams.id;
        $scope.messages = messageSrv.collect();
        $scope.timeoutPromise = null;
        $scope.showMessageItemIds = config.showMessageItemIds;
        $scope.unread = [];

        $scope.getThread = function () {
            var url = Urls['messaging_api:get_thread']() + '?miid=' + $routeParams.id;
            $timeout.cancel($scope.timeoutPromise);
            genericSrv.genericGet(url).
                then(function (data) {
                    $scope.subject = data.subject;
                    $scope.thread = data.messages;
                    $scope.storeUnread();
                    $scope.total = data.total;
                    if ($scope.total === 0) {
                        $scope.messages.info = config.trans.empty_thread;
                    }
                    $scope.timeoutPromise = $timeout(function () {
                        $scope.getThread();
                    }, 10000);
                }, function (error) {
                    messageSrv.messages[error.type] = error.errorMessage;
                    $location.path('/');
                });
        };

        $scope.getThread();

        $scope.storeUnread = function () {
            var i, count;
            for (i = 0, count = $scope.thread.length; i < count; ++i) {
                if (!$scope.thread[i].read && $scope.unread.indexOf($scope.thread[i].id) === -1) {
                    $scope.unread.push($scope.thread[i].id);
                }
            }
        };

        $scope.isRead = function (email) {
            return $scope.unread.indexOf(email.id) === -1;
        };

        $scope.openModal = function (uid, miid) {
            $timeout.cancel($scope.timeoutPromise);
            $scope.miid = miid;
            jQuery('#' + uid).modal({});
        };

        $scope.cancelDeleteMessage = function (uid) {
            var elem = jQuery('#' + uid);
            elem.off('hidden.bs.modal');
            elem.on('hidden.bs.modal', function () {
                $scope.getThread();
            });
            elem.modal('hide');
        };

        $scope.deleteOne = function (uid) {
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
                    }, function (error) {
                        $scope.messages[error.type] = error.errorMessage;
                    }).
                    finally(function () {
                        $scope.getThread();
                    });
            });
            elem.modal('hide');
        };

        $scope.deleteAll = function (uid) {
            var url,
                elem = jQuery('#' + uid);
            elem.off('hidden.bs.modal');
            elem.on('hidden.bs.modal', function () {
                if (!$scope.total) {
                    return;
                }
                url = Urls['messaging_api:delete_message_item']() + '?miid=' + $scope.thread[0].id + '&thread';
                genericSrv.genericGet(url).
                    then(function (data) {
                        messageSrv.messages.success = data.successMessage;
                        $location.path('/');
                    }, function (error) {
                        $scope.messages[error.type] = error.errorMessage;
                        $scope.getThread();
                    });
            });
            elem.modal('hide');
        };

        $scope.$on('$destroy', function () {
            $timeout.cancel($scope.timeoutPromise);
        });
    }
]);
