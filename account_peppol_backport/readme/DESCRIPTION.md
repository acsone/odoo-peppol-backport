This is a backport of the `account_peppol` addon of Odoo 17: 
- the registration/unregistration logic and UI;
- the logic to determine if a partner is registered on the Peppol network and
  the supported formats;
- the cron to receive documents and create Vendor Bills;
- a Send via Peppol option and button in the invoice Send & Print wizard;
- a method to send a invoice to the access point (the actual sending logic
  is provided by other modules, see the Installation section);
- the cron to update the status of Peppol document sent to the network.

There are a few differences from the Odoo 17 module:
- Only the the ``ubl_bis3`` format is supported for now.
- Sending is done either synchronously or asynchronously via queue job (one job
  per invoice), where in Odoo 17 sending is done asynchrounously in a cron job
  with multiple invoices sent in one API call.
- The flag `is_move_sent` is set when the Peppol status of an Invoice is set to
  `done` by the batch that updates the statuses. The upstream module does not
  handle the `is_move_sent` flag.
- It can log the sent XML file in the chatter when a
  `account_peppol_backport.log_sent_xml` system parameter is set to a non empty value.

Note that when doing the registration with this module, the company is registered as
a participant, so a receiver. In v18, it is possible to register as a sender only.
