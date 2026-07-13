from frappe.model.document import Document


class MaestroCreditAccount(Document):
    def validate(self):
        # remaining is always derived — never trust a hand-edited value.
        self.remaining_credits = max(0, (self.total_credits or 0) - (self.used_credits or 0))
