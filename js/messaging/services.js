'use strict';

var app = angular.module('messagingApp.services', []);

app.service('inboxSortSrv', function () {
    this.sortField = 'date';
    this.sortDirection = 'desc';

    this.toFlags = function () {
        return {
            sender: this.sortField === 'sender',
            senderAsc: this.sortField === 'sender' && this.sortDirection === 'asc',
            senderDesc: this.sortField === 'sender' && this.sortDirection === 'desc',
            date: this.sortField === 'date',
            dateAsc: this.sortField === 'date' && this.sortDirection === 'asc',
            dateDesc: this.sortField === 'date' && this.sortDirection === 'desc'
        };
    };

    this.toggleSortDirection = function () {
        if (this.sortDirection === 'asc') {
            this.sortDirection = 'desc';
        } else {
            this.sortDirection = 'asc';
        }
    };
});
