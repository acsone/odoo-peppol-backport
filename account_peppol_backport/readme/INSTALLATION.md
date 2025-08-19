To be able to send invoices to the PEPPOL network, two modules needs to be installed in addition to this one.

One module to define how the XML format is generated:
- `account_peppol_send_format_odoo`

One module to define how the send operation is executed
- `account_peppol_send_immediate` to send immediately when the user clicks "Send via PEPPOL"
- `account_peppol_send_queue_job` to send asynchronously via the job queue
  (recommended unless you cannot install `queue_job`)
