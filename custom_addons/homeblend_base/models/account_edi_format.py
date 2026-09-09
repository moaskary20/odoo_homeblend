from odoo import models


class AccountEdiFormat(models.Model):
    _inherit = "account.edi.format"

    def _get_move_applicability(self, move):
        """Do not block invoicing until the journal is actually configured for ETA."""
        self.ensure_one()
        if self.code == "eg_eta":
            journal = move.journal_id
            if not (journal.l10n_eg_branch_id and journal.l10n_eg_branch_identifier and journal.l10n_eg_activity_type_id):
                return {}
        return super()._get_move_applicability(move)
