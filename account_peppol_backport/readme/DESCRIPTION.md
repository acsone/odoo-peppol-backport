This is a backport of the `account_peppol` addon of Odoo 17: 
- the registration/unregistration logic and UI;
- the logic to determine if a partner is registered on the Peppol network and
  the supported formats (``ubl_bis3`` only for now);
- the cron to receive documents and create Vendor Bills;
- a Send via Peppol option and button in the invoice Send & Print wizard;
- a method to send a invoice to the access point (the actual sending logic
  is provided by other modules, see the Installation section);
- the cron to update the status of Peppol document sent to the network.

The following differs from the Odoo 17 module:
- The flag `is_move_sent` is set when the Peppol status of an Invoice is set to
  `done` by the batch that updates the statuses. The upstream module does not
  handle the `is_move_sent` flag.
