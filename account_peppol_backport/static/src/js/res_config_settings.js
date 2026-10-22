// Copyright 2026 SPI
// License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

odoo.define('account_peppol_backport.settings', function (require) {
    'use strict';

    const BaseSettingsController = require('base.settings').Controller;
    const FormController = require('web.FormController');
    const peppolInputButtons = new Set([
        'button_create_peppol_proxy_user',
        'button_update_peppol_user_data',
        'button_send_peppol_verification_code',
        'button_check_peppol_verification_code',
    ]);

    BaseSettingsController.include({
        _onButtonClicked: function (ev) {
            if (peppolInputButtons.has(ev.data.attrs.name)) {
                // save Peppol input before the action, without the settings discard/reload flow
                return FormController.prototype._onButtonClicked.apply(this, arguments);
            }
            return this._super.apply(this, arguments);
        },
    });
});
