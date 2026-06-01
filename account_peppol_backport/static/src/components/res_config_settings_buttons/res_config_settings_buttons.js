/** @odoo-module **/

/* eslint-disable sort-imports */
import { _t } from "@web/core/l10n/translation";
import { escape } from "@web/core/utils/strings";
import { registry } from "@web/core/registry";
import { pick } from "@web/core/utils/objects";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

import { Component, markup } from "@odoo/owl";


class PeppolSettingsButtons extends Component {
    setup() {
        super.setup();
        this.dialogService = useService("dialog");
        this.notification = useService("notification");
    }

    get proxyState() {
        return this.props.record.data.account_peppol_proxy_state;
    }

    get migrationPrepared() {
        return this.props.record.data.account_peppol_proxy_state === "receiver" && Boolean(this.props.record.data.account_peppol_migration_key);
    }

    get ediMode() {
        const demo_if_demo_identifier = this.props.record.data.peppol_eas === 'odemo' ? "demo": false
        return demo_if_demo_identifier || this.props.record.data.edi_mode || this.props.record.data.account_peppol_edi_mode;
    }

    get modeConstraint() {
        return this.props.record.data.account_peppol_mode_constraint;
    }

    get createUserButtonLabel() {
        const modes = {
            demo: _t("Activate Peppol (Demo)"),
            test: _t("Activate Peppol (Test)"),
            prod: _t("Activate Peppol"),
        }
        return modes[this.ediMode];
    }

    get deregisterUserButtonLabel() {
        return _t("Remove from Peppol");
    }

    async _callConfigMethod(methodName, save = false) {
        if (save) {
            await this._save();
        }
        this.env.onClickViewButton({
            clickParams: {
                name: methodName,
                type: "object",
                noSaveDialog: true,
            },
            getResParams: () =>
                pick(this.env.model.root, "context", "evalContext", "resModel", "resId", "resIds"),
        });
    }

    async _save () {
        this.env.model.root.save({ reload: false });
    }

    showConfirmation(warning, methodName) {
        const message = _t(warning);
        const confirmMessage = _t("You will not be able to send or receive Peppol documents in Odoo anymore. Are you sure you want to proceed?");
        this.dialogService.add(ConfirmationDialog, {
            body: markup(
                `<div class="text-danger">${escape(message)}</div>
                <div class="text-danger">${escape(confirmMessage)}</div>`
            ),
            confirm: async () => {
                await this._callConfigMethod(methodName);
            },
            cancel: () => { }, // eslint-disable-line
        });
    }

    deregister() {
        if (this.ediMode === 'demo' || !['sender', 'smp_registration', 'receiver'].includes(this.proxyState)) {
            this._callConfigMethod("button_deregister_peppol_participant");
        } else if (['sender', 'smp_registration', 'receiver'].includes(this.proxyState)) {
            this.showConfirmation(
                "This will delete your Peppol registration.",
                "button_deregister_peppol_participant"
            )
        }
    }

    async updateDetails() {
        // Avoid making users click save on the settings
        // and then clicking the update button
        // changes on both the client side and the iap side need to be saved within one method
        await this._callConfigMethod("button_update_peppol_user_data", true);
        this.notification.add(
            _t("Contact details were updated."),
            { type: "success" }
        );
    }

    async checkCode() {
        // Avoid making users click save on the settings
        // and then clicking the confirm button to check the code
        await this._callConfigMethod("button_create_peppol_proxy_user", true);
    }

    async createReceiver() {
        await this._callConfigMethod("button_peppol_smp_registration", true);
    }
}

PeppolSettingsButtons.template = "account_peppol_backport.ActionButtons";
PeppolSettingsButtons.props = {
    ...standardWidgetProps,
};
registry.category("view_widgets").add("peppol_settings_buttons", PeppolSettingsButtons);
