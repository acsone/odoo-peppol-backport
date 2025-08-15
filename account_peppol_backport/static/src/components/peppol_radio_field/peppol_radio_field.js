/** @odoo-module **/

/* eslint-disable sort-imports */
import { evaluateExpr } from "@web/core/py_js/py";
import { RadioField, radioField } from "@web/views/fields/radio/radio_field";
import { registry } from "@web/core/registry";

class PeppolRadioField extends RadioField {
    setup() {
        super.setup()
        this.initialSelection = this.props.record.data[this.props.name];
        this.readonlyItems = evaluateExpr(this.props.readonlyItems || "[]", this.props.record.evalContext);
        this.hiddenItems = evaluateExpr(this.props.hiddenItems || "[]", this.props.record.evalContext).filter(item => (item != this.initialSelection));
    }

    get items() {
        return super.items.filter(item => !(this.hiddenItems.includes(item[0])))
    }
}

PeppolRadioField.template = "account_peppol_regitration.PeppolRadioField";
PeppolRadioField.props = {
    ...RadioField.props,
    hiddenItems: { type: String, optional: true },
    readonlyItems: { type: String, optional: true },
};

const peppolRadioField = {
    ...radioField,
    component: PeppolRadioField,
    extractProps: ({attrs, options}, dynamicInfo) => {
        return {
            hiddenItems: attrs.hidden_items || "[]",
            readonlyItems: attrs.readonly_items  || "[]",
            ...radioField.extractProps({attrs, options}, dynamicInfo),
        }
    },
}

registry.category("fields").add("account_peppol_radio_field", peppolRadioField);
