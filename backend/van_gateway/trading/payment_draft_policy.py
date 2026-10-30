"""Apply the existing payment-instrument owner to unapproved draft metadata.

Exact money integers, clocks and fixed digest references have typed numeric or
content-reference meanings. Free text and asset/provider/owner identifiers are
checked before retention. Unknown instrument fields refuse in the strict draft
parser. This is not beneficiary, provider, quote or payment qualification.
"""
import json

from van_gateway.automation.payments import PaymentBoundaryError,assert_no_instrument
from van_gateway.owner_privacy import _SECRET


def guard_payment_draft(intent):
    quote=intent.quote;beneficiary=quote.beneficiary
    money=[quote.amount,quote.quoted_debit,*[fee.amount for fee in quote.fees]]
    metadata={'request_id':intent.request_id,'operation':intent.operation,
        'provider':beneficiary.provider,'owner_ref':beneficiary.owner_ref,'reference':quote.reference,
        'fee_ids':[fee.fee_id for fee in quote.fees],
        'money_metadata':[{'currency':m.currency,'asset_ref':m.asset_ref} for m in money]}
    if _SECRET.search(json.dumps(metadata,ensure_ascii=False)):
        raise PaymentBoundaryError('credential_in_funding_draft_metadata')
    assert_no_instrument(metadata,context='funding_draft_metadata')
